"""PAP1 interval migration and guards on disposable, actually migrated PostgreSQL."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.clock as clock_module
from core.clock import BUSINESS_TZ, business_now
from expansion import session_payment_service, ticket_payment_access
from expansion.session_payment_models import SessionFeeQuote
from expansion.session_payment_schemas import SessionFeeQuoteCreate, SessionPaymentConfig
from expansion.simplified_customer_models import SessionPaymentAccess, SessionPaymentAccessHistory, SessionTicketCredential
from expansion.site_models import ParkingSite
from models import ParkingSession, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone
from postgres_readiness import check_postgres_readiness
from services.parking_service import ParkingService
from test_postgres_integration import POSTGRES_TEST_URL, _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Requires isolated PostgreSQL service")
ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _schema09_postgres(monkeypatch):
    """Reuse the protected temporary-DB helper, stopping its first migration at09."""
    original = subprocess.run
    calls = []

    def stop_at09(command, **kwargs):
        arguments = list(command)
        assert arguments[-2:] == ["upgrade", "head"] and "alembic" in arguments
        calls.append(arguments)
        arguments[-1] = "20260923_09"
        return original(arguments, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "run", stop_at09)
        with _isolated_checkout_postgres() as engine:
            patch.undo()  # Subsequent upgrade executes the real head normally.
            assert len(calls) == 1
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260923_09"
                assert "session_payment_access_history" not in inspect(connection).get_table_names()
            yield engine


def _upgrade_head(engine):
    # The context manager above validates CI, test role and loopback before it
    # creates this generated database; never accept an application's URL here.
    assert engine.url.database.startswith("parkingai_checkout_")
    assert engine.url.username == "parkingai_test" and engine.url.host in {"127.0.0.1", "localhost", "::1"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "backend/alembic.ini"), "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "DATABASE_URL": engine.url.render_as_string(hide_password=False)},
        capture_output=True, text=True, timeout=60, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _seed_pending(engine, monkeypatch):
    instant = [business_now().replace(microsecond=0)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = instant[0].replace(tzinfo=BUSINESS_TZ)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(clock_module, "datetime", Clock)
    with Session(engine) as db:
        admin_role, customer_role = Role(name="admin"), Role(name="customer")
        kind, site = VehicleType(name="PAP history car"), ParkingSite(name="PAP history site")
        db.add_all([admin_role, customer_role, kind, site])
        db.flush()
        operator = User(username="pap-history-admin", password_hash="unused", full_name="Admin", role_id=admin_role.id)
        payer = User(username="pap-history-payer", password_hash="unused", full_name="Payer", role_id=customer_role.id)
        zone = Zone(name="PAP history zone", site_id=site.id, capacity=1)
        vehicle = Vehicle(license_plate="30A-123.45", vehicle_type_id=kind.id)
        db.add_all([operator, payer, zone, vehicle])
        db.flush()
        slot = ParkingSlot(slot_name="PAP-HISTORY-1", vehicle_type_id=kind.id, zone_id=zone.id)
        db.add_all([slot, PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=5000,
                                     effective_date=instant[0].date())])
        db.commit()
        stay = ParkingService(db).check_in(vehicle.license_plate, kind.id, operator.id, parking_slot_id=slot.id)
        credential = SessionTicketCredential(session_id=stay["session_id"], created_at=instant[0])
        db.add(credential)
        db.flush()
        access = SessionPaymentAccess(user_id=payer.id, session_id=stay["session_id"],
            vehicle_id=vehicle.id, customer_snapshot_id=None, credential_version=credential.version,
            created_at=instant[0], expires_at=instant[0] + timedelta(hours=24))
        db.add(access)
        db.commit()
        started, ended = access.created_at, access.expires_at
        instant[0] = ended - timedelta(minutes=1)
        proposal = session_payment_service.create_quote(db, payer, stay["session_id"],
            SessionFeeQuoteCreate(request_id="postgres-history-pending"),
            SimpleNamespace(PAYOS_ENABLED=True, PAYOS_SITE_ID=site.id),
            quote_settings=SessionPaymentConfig(_env_file=None, SESSION_FEE_QUOTE_TTL_SECONDS=300))
        return SimpleNamespace(clock=instant, access_id=access.id, payer_id=payer.id,
            session_id=stay["session_id"], vehicle_id=vehicle.id, quote_id=proposal.id,
            started=started, ended=ended, received=instant[0] + timedelta(seconds=30))


def _renew_like_old_application(engine, ctx, start):
    """The previous service rewrote one grant; no new helper/archive write here."""
    end = start + timedelta(hours=24)
    with engine.begin() as connection:
        connection.execute(text("UPDATE session_payment_access SET created_at=:start, expires_at=:end, "
                                "revoked_at=NULL WHERE id=:id"),
                           {"start": start, "end": end, "id": ctx.access_id})
    ctx.clock[0] = start
    return end


def _authorized(db, ctx, *, at=None):
    return ticket_payment_access.valid_access(db, db.get(User, ctx.payer_id),
        db.get(ParkingSession, ctx.session_id), db.get(Vehicle, ctx.vehicle_id), at=at)


def test_postgres_schema09_pending_quote_survives_upgrade_and_old_style_renewal(monkeypatch):
    with _schema09_postgres(monkeypatch) as engine:
        ctx = _seed_pending(engine, monkeypatch)
        with engine.connect() as connection:
            before_grant = dict(connection.execute(text("SELECT * FROM session_payment_access")).mappings().one())
            before_quote = dict(connection.execute(text("SELECT * FROM session_fee_quotes")).mappings().one())
            before_stay = dict(connection.execute(text("SELECT * FROM parking_sessions")).mappings().one())
        _upgrade_head(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260927_10"
            assert dict(connection.execute(text("SELECT * FROM session_payment_access")).mappings().one()) == before_grant
            assert dict(connection.execute(text("SELECT * FROM session_fee_quotes")).mappings().one()) == before_quote
            assert dict(connection.execute(text("SELECT * FROM parking_sessions")).mappings().one()) == before_stay
            assert connection.scalar(text("SELECT COUNT(*) FROM session_payment_access_history")) == 0
        renewal = ctx.ended + timedelta(seconds=30)
        current_end = _renew_like_old_application(engine, ctx, renewal)
        with Session(engine) as db:
            archived = db.scalars(select(SessionPaymentAccessHistory)).one()
            assert (archived.access_id, archived.created_at, archived.expires_at, archived.revoked_at) == (
                ctx.access_id, ctx.started, ctx.ended, None)
            assert archived.credential_version == before_grant["credential_version"]
            assert _authorized(db, ctx, at=ctx.received) is not None
            assert _authorized(db, ctx) is not None
            assert session_payment_service.fulfillment_problem(db, db.get(SessionFeeQuote, ctx.quote_id),
                SimpleNamespace(received_at=ctx.received)) is None
            for denied_at in [ctx.started - timedelta(microseconds=1), ctx.ended, renewal - timedelta(microseconds=1)]:
                assert _authorized(db, ctx, at=denied_at) is None
            ctx.clock[0] = current_end
            assert _authorized(db, ctx) is None, "Historical intervals must not extend browser authority."
            assert _authorized(db, ctx, at=ctx.received) is not None
            assert db.get(SessionFeeQuote, ctx.quote_id).status == "pending"
        check_postgres_readiness(engine, deep=True)


def test_postgres_revocation_then_regrant_never_revives_history_and_guards_reject_rewrites(monkeypatch):
    with _isolated_checkout_postgres() as engine:
        ctx = _seed_pending(engine, monkeypatch)
        renewal = ctx.ended + timedelta(seconds=30)
        _renew_like_old_application(engine, ctx, renewal)
        with Session(engine) as db:
            for statement in [
                "UPDATE session_payment_access_history SET expires_at=expires_at+INTERVAL '1 second'",
                "UPDATE session_payment_access_history SET created_at=created_at-INTERVAL '1 second'",
                "DELETE FROM session_payment_access_history",
            ]:
                with pytest.raises(IntegrityError, match="ticket access history"):
                    with db.begin_nested():
                        db.execute(text(statement))
            assert _authorized(db, ctx, at=ctx.received) is not None
            revoked = renewal + timedelta(seconds=10)
            db.execute(text("UPDATE session_payment_access SET revoked_at=:at WHERE id=:id"),
                       {"at": revoked, "id": ctx.access_id})
            db.commit()
            assert db.scalars(select(SessionPaymentAccessHistory)).one().revoked_at == revoked
            assert _authorized(db, ctx, at=ctx.received) is None
            with pytest.raises(IntegrityError, match="ticket access history immutable"):
                with db.begin_nested():
                    db.execute(text("UPDATE session_payment_access_history SET revoked_at=NULL"))
            db.rollback()
        # Same credential and snapshots, valid user/session: only the durable
        # revocation of the archived interval prevents resurrecting old money.
        _renew_like_old_application(engine, ctx, renewal + timedelta(minutes=1))
        with Session(engine) as db:
            assert _authorized(db, ctx) is not None
            assert _authorized(db, ctx, at=ctx.received) is None
            assert session_payment_service.fulfillment_problem(db, db.get(SessionFeeQuote, ctx.quote_id),
                SimpleNamespace(received_at=ctx.received)) == "session_payment_access_revoked"
            assert db.scalars(select(SessionPaymentAccessHistory)).one().revoked_at == revoked
            with pytest.raises(IntegrityError, match="ticket access history source invalid"):
                with db.begin_nested():
                    db.execute(text("INSERT INTO session_payment_access_history "
                        "(access_id,created_at,expires_at,credential_version,vehicle_id,customer_snapshot_id) "
                        "SELECT id,created_at-INTERVAL '1 day',expires_at,credential_version,vehicle_id,customer_snapshot_id "
                        "FROM session_payment_access WHERE id=:id"), {"id": ctx.access_id})
