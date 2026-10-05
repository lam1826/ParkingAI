"""CL-ONLINE fixes 05/10: payOS worker selection order (#51) and loop resilience (#84)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import core.clock as clock
import models  # noqa: F401  registers all tables
import expansion.online_payment_worker as worker
from database import Base
from expansion.online_payment_models import OnlinePaymentLink

CHANNEL = "c" * 64
NOW = datetime(2026, 10, 5, 12, 0, 0)


@pytest.fixture
def frozen(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = NOW.replace(tzinfo=clock.BUSINESS_TZ)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Clock)


@pytest.fixture
def scratch_db():
    """Private in-memory database: link rows without parent orders (fixture only)."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for (name,) in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='online_payment_links'").all():
            conn.exec_driver_sql(f"DROP TRIGGER {name}")
        conn.commit()
    with Session(engine) as db:
        yield db
    engine.dispose()


def _link(db, identity, state, last_checked_at):
    db.add(OnlinePaymentLink(id=identity, order_id=f"order-{identity}", site_id=1, channel=CHANNEL,
        receiver_digest="r" * 64, amount=1000, currency="VND", return_url="https://x.example/r",
        cancel_url="https://x.example/c", expires_at=NOW - timedelta(hours=1), state=state,
        last_checked_at=last_checked_at))


CONFIG = SimpleNamespace(PAYOS_ENABLED=True, channel=CHANNEL, PAYOS_SITE_ID=1)


# --- #51 -----------------------------------------------------------------

def test_postgres_selection_puts_never_checked_rows_first():
    now = NOW
    links_sql = str(worker.due_links_query(CONFIG, now, 50).compile(dialect=postgresql.dialect()))
    inbox_sql = str(worker.due_inbox_query(now, 50).compile(dialect=postgresql.dialect()))
    assert "online_payment_links.last_checked_at ASC NULLS FIRST" in links_sql
    assert "online_payment_processing.next_attempt_at ASC NULLS FIRST" in inbox_sql


def test_unresolved_links_are_reconciled_before_terminal_links(frozen, scratch_db, monkeypatch):
    _link(scratch_db, 1, "expired", NOW - timedelta(minutes=10))
    _link(scratch_db, 2, "cancelled", NOW - timedelta(minutes=9))
    _link(scratch_db, 3, "unknown", NOW - timedelta(minutes=1))
    _link(scratch_db, 4, "creating", None)
    scratch_db.commit()
    picked = []
    monkeypatch.setattr(worker, "reconcile_link_for_worker", lambda db, link_id, config, gateway: picked.append(link_id))
    worker.run_online_payment_maintenance(scratch_db, CONFIG, None, limit=2)
    assert picked == [4, 3]


# --- #84 -----------------------------------------------------------------

def test_run_loop_survives_a_transient_database_error(monkeypatch):
    calls, sleeps, printed, sessions = [], [], [], []

    class FakeSession:
        def __init__(self):
            self.rolled_back = 0
            sessions.append(self)

        def rollback(self):
            self.rolled_back += 1

        def close(self):
            pass

    def flaky(db, config, gateway, *, limit):
        calls.append(limit)
        if len(calls) == 1:
            raise OperationalError("SELECT 1", {}, Exception("database is locked"))
        return {"disabled": False, "handled": 0, "retry": 0, "reconciled": 0}

    monkeypatch.setattr(worker, "run_online_payment_maintenance", flaky)
    worker.run_worker_loop(FakeSession, CONFIG, None, limit=5, poll_seconds=10, once=False,
        sleep=sleeps.append, emit=printed.append, max_cycles=3)
    assert len(calls) == 3
    assert sessions[0].rolled_back >= 1
    assert sleeps == [10, 10]
    assert sum('"handled": 0' in line for line in printed) == 2
    assert any('"error": "cycle_failed"' in line for line in printed)


def test_item_recovery_write_failure_does_not_abort_the_cycle(frozen, scratch_db, monkeypatch):
    from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentProcessing
    scratch_db.execute(OnlinePaymentInbox.__table__.insert().values(id="inbox-1", link_id=None, site_id=1,
        channel=CHANNEL, source="webhook", order_code=1, payment_link_id="L", reference="R", amount=1000,
        currency="VND", receiver_digest="r" * 64, transaction_time="t", payload_digest="d" * 64, received_at=NOW))
    scratch_db.execute(OnlinePaymentProcessing.__table__.insert().values(id="inbox-1", status="received", attempts=0))
    scratch_db.commit()

    def boom(*args, **kwargs):
        raise OperationalError("UPDATE", {}, Exception("connection lost"))

    monkeypatch.setattr(worker, "process_inbox", boom)
    original_get = scratch_db.get
    monkeypatch.setattr(scratch_db, "get", lambda *args, **kwargs: boom())
    result = worker.run_online_payment_maintenance(scratch_db, CONFIG, None, limit=5)
    monkeypatch.setattr(scratch_db, "get", original_get)
    assert result["retry"] >= 1 and result["handled"] == 0


class _QuietSession:
    def rollback(self):
        pass

    def close(self):
        pass


def _cycle(fail):
    def run(db, config, gateway, *, limit):
        if fail:
            raise OperationalError("SELECT 1", {}, Exception("database is locked"))
        return {"disabled": False, "handled": 0, "retry": 0, "reconciled": 0}
    return run


@pytest.mark.parametrize("fail", [True, False])
def test_once_reports_whether_its_single_cycle_failed(monkeypatch, fail):
    monkeypatch.setattr(worker, "run_online_payment_maintenance", _cycle(fail))
    sleeps, printed = [], []
    result = worker.run_worker_loop(_QuietSession, CONFIG, None, once=True, sleep=sleeps.append, emit=printed.append)
    assert result is fail and sleeps == [] and len(printed) == 1


@pytest.mark.parametrize("fail, code", [(True, 1), (False, 0)])
def test_once_cli_exits_non_zero_when_the_cycle_failed(monkeypatch, fail, code):
    """Rework of #84: --once (P5_OPERATIONS.md) must expose a failed cycle by exit status."""
    import database
    import expansion.online_payment_schemas as schemas
    import expansion.payos_gateway as gateway_module
    settings = SimpleNamespace(PAYOS_ENABLED=True, channel=CHANNEL, PAYOS_SITE_ID=1, adapter_settings=lambda: None)
    monkeypatch.setattr(schemas, "get_online_payment_config", lambda: settings)
    monkeypatch.setattr(gateway_module, "PayOSGateway", lambda adapter_settings, transport: object())
    monkeypatch.setattr(database, "SessionLocal", _QuietSession)
    monkeypatch.setattr(worker, "run_online_payment_maintenance", _cycle(fail))
    assert worker.main(["--once"]) == code


def test_cli_stays_disabled_without_payos(monkeypatch, capsys):
    import expansion.online_payment_schemas as schemas
    monkeypatch.setattr(schemas, "get_online_payment_config", lambda: SimpleNamespace(PAYOS_ENABLED=False))
    assert worker.main(["--once"]) == 0
    assert '"disabled": true' in capsys.readouterr().out
