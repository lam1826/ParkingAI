"""Candidate-only billing rollout keeps unknown legacy tariffs unknown."""
import ast
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from core.billing_guards import BILLING_SQLITE_GUARDS, SNAPSHOT_COLUMN_TYPES, BILLING_POSTGRES_GUARD_SQL
from core.session_event_guards import SESSION_EVENT_SQLITE_GUARDS
from expansion.timed_parking_guards import TIMED_SQLITE_GUARDS
from expansion.session_payment_guards import SESSION_PAYMENT_SQLITE_GUARDS
from database import PRE_SNAPSHOT_TRIGGER_SQL, SNAPSHOT_REVISED_TRIGGER_SQL
from db_rollout import check_database_readiness, initialize_database, migrate_copy
from test_finance_rollout import _seed_legacy_finance


def _legacy_database(path):
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        _seed_legacy_finance(engine)
        with engine.begin() as conn:
            for name in SESSION_PAYMENT_SQLITE_GUARDS:
                conn.exec_driver_sql(f"DROP TRIGGER {name}")
            for name in TIMED_SQLITE_GUARDS:
                conn.exec_driver_sql(f"DROP TRIGGER {name}")
            for name in SESSION_EVENT_SQLITE_GUARDS:
                conn.exec_driver_sql(f"DROP TRIGGER {name}")
            conn.exec_driver_sql("DROP TABLE parking_session_events")
            for name in BILLING_SQLITE_GUARDS:
                conn.exec_driver_sql(f"DROP TRIGGER {name}")
            for name, sql in PRE_SNAPSHOT_TRIGGER_SQL.items():
                conn.exec_driver_sql(f"DROP TRIGGER {name}")
                conn.exec_driver_sql(sql)
            for name in SNAPSHOT_COLUMN_TYPES:
                conn.exec_driver_sql(f"ALTER TABLE parking_sessions DROP COLUMN {name}")
            conn.exec_driver_sql("INSERT INTO price_configs (vehicle_type_id, ticket_type, price, effective_date, is_active) VALUES (1, 'HOURLY', 25000, '2026-01-01', 1)")
            conn.exec_driver_sql("INSERT INTO parking_sessions (id, vehicle_id, staff_in_id, status, check_in_time) VALUES ('legacy-active', 1, 1, 'active', '2026-09-15 23:00:00')")
    finally:
        engine.dispose()


def test_snapshot_rollout_preserves_source_and_null_legacy_history(tmp_path):
    source, target = tmp_path / "old.db", tmp_path / "new.db"
    _legacy_database(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    migrate_copy(source, target)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    for _ in range(2):
        initialize_database(target)
        engine = create_engine("sqlite:///" + target.as_posix())
        try:
            columns = {item["name"]: item for item in inspect(engine).get_columns("parking_sessions")}
            assert all(columns[name]["nullable"] and columns[name]["default"] is None for name in SNAPSHOT_COLUMN_TYPES)
            with engine.begin() as conn:
                values = conn.exec_driver_sql("SELECT id, status, parking_fee, " + ", ".join(SNAPSHOT_COLUMN_TYPES) + " FROM parking_sessions ORDER BY id").all()
                assert values == [("legacy-active", "active", None, None, None, None, None, None),
                                  ("legacy-session", "completed", 25000, None, None, None, None, None)]
                with pytest.raises(IntegrityError, match="active parking session uses price"):
                    conn.exec_driver_sql("UPDATE price_configs SET price = 1 WHERE id = 1")
                # No retroactive monthly coverage or rate is invented on old stays.
                with pytest.raises(IntegrityError, match="snapshot immutable"):
                    conn.exec_driver_sql("UPDATE parking_sessions SET billing_policy_version = 'entry-v1' WHERE id = 'legacy-active'")
            check_database_readiness(engine)
        finally:
            engine.dispose()


def test_unknown_old_guard_definition_refuses_copy_without_mutation(tmp_path):
    source, target = tmp_path / "unknown.db", tmp_path / "target.db"
    _legacy_database(source)
    engine = create_engine("sqlite:///" + source.as_posix())
    try:
        with engine.begin() as conn:
            name = next(iter(PRE_SNAPSHOT_TRIGGER_SQL))
            conn.exec_driver_sql(f"DROP TRIGGER {name}")
            conn.exec_driver_sql(f"CREATE TRIGGER {name} BEFORE UPDATE ON price_configs BEGIN SELECT 1; END")
    finally:
        engine.dispose()
    before = source.read_bytes()
    with pytest.raises(RuntimeError, match="sai định nghĩa"):
        migrate_copy(source, target)
    assert source.read_bytes() == before and not target.exists()


def test_active_snapshot_survives_tariff_removal_and_readiness_restart(tmp_path):
    path = tmp_path / "snapshot-restart.db"
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        _seed_legacy_finance(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql("INSERT INTO price_configs (id, vehicle_type_id, ticket_type, price, effective_date, is_active) VALUES (701, 1, 'HOURLY', 25000, '2026-01-01', 1)")
            conn.exec_driver_sql("""INSERT INTO parking_sessions
                (id, vehicle_id, staff_in_id, status, check_in_time, billing_policy_version,
                 rate_config_id, rate_ticket_type, rate_unit_price, rate_effective_date)
                VALUES ('snapshot-active', 1, 1, 'active', '2026-09-15 23:00:00',
                        'entry-v1', 701, 'HOURLY', 25000, '2026-01-01')""")
            conn.exec_driver_sql("DELETE FROM price_configs WHERE id = 701")
        check_database_readiness(engine)
        engine.dispose()  # Candidate publication requires a cold Windows file.
        initialize_database(path)
        check_database_readiness(engine)
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT status, rate_config_id, rate_unit_price FROM parking_sessions WHERE id='snapshot-active'").one() == ("active", 701, 25000)
    finally:
        engine.dispose()


@pytest.fixture
def snapshot_connection():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            cols = ", ".join(name + " " + kind for name, kind in SNAPSHOT_COLUMN_TYPES.items())
            conn.exec_driver_sql("CREATE TABLE parking_sessions (id TEXT PRIMARY KEY, check_in_time TEXT, monthly_pass_id INTEGER, monthly_coverage_end TEXT, " + cols + ")")
            for name, statement in BILLING_SQLITE_GUARDS.items():
                if "cancelled" not in name:
                    conn.exec_driver_sql(statement)
            yield conn
    finally:
        engine.dispose()


@pytest.mark.parametrize("field,value", [
    ("billing_policy_version", None), ("billing_policy_version", "entry-v2"),
    ("rate_config_id", 0), ("rate_config_id", None), ("rate_unit_price", None),
    ("rate_unit_price", -1), ("rate_unit_price", 1.5), ("rate_unit_price", 2**53),
    ("rate_ticket_type", "weekly"), ("rate_effective_date", "2026-02-30"),
    ("rate_effective_date", "2027-01-01"), ("monthly_pass_id", 1),
])
def test_db_rejects_partial_or_invalid_snapshot(snapshot_connection, field, value):
    values = {"id": "new", "check_in_time": "2026-09-15 23:00:00", "monthly_pass_id": None,
              "monthly_coverage_end": None, "billing_policy_version": "entry-v1", "rate_config_id": 1,
              "rate_unit_price": 25000, "rate_ticket_type": "HOURLY", "rate_effective_date": "2026-09-15"}
    values[field] = value
    with pytest.raises(IntegrityError, match="snapshot invalid"):
        snapshot_connection.exec_driver_sql("INSERT INTO parking_sessions (" + ", ".join(values) + ") VALUES (" + ", ".join("?" for _ in values) + ")", tuple(values.values()))


def test_snapshot_cannot_be_cleared_changed_or_replaced(snapshot_connection):
    conn = snapshot_connection
    conn.exec_driver_sql("INSERT INTO parking_sessions (id, check_in_time, billing_policy_version, rate_config_id, rate_unit_price, rate_ticket_type, rate_effective_date) VALUES ('new', '2026-09-15 23:00:00', 'entry-v1', 1, 25000, 'HOURLY', '2026-09-15')")
    for sql in ["UPDATE parking_sessions SET rate_unit_price = 1 WHERE id = 'new'",
                "DELETE FROM parking_sessions WHERE id = 'new'",
                "UPDATE parking_sessions SET " + ", ".join(name + " = NULL" for name in SNAPSHOT_COLUMN_TYPES) + " WHERE id = 'new'",
                "INSERT OR REPLACE INTO parking_sessions (id, check_in_time) VALUES ('new', '2026-09-15 23:00:00')"]:
        with pytest.raises(IntegrityError, match="snapshot (immutable|history)"):
            conn.exec_driver_sql(sql)
    conn.exec_driver_sql("INSERT INTO parking_sessions (id, check_in_time) VALUES ('legacy', '2026-09-15 23:00:00')")
    with pytest.raises(IntegrityError, match="snapshot immutable"):
        conn.exec_driver_sql("INSERT OR REPLACE INTO parking_sessions (id, check_in_time, billing_policy_version, rate_config_id, rate_unit_price, rate_ticket_type, rate_effective_date) VALUES ('legacy', '2026-09-15 23:00:00', 'entry-v1', 1, 25000, 'HOURLY', '2026-09-15')")


def test_frozen_postgres_migration_retains_known_guard_contracts():
    path = Path(__file__).resolve().parents[1] / "backend/alembic/versions/20260915_01_billing_snapshot.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    # P1 remains frozen; P4 extends the live guard with a new prepaid policy.
    assert constants["BILLING_POSTGRES_GUARD_SQL"] == BILLING_POSTGRES_GUARD_SQL.replace(
        "NEW.billing_policy_version IN ('entry-v1','prepaid-window-v1')", "NEW.billing_policy_version = 'entry-v1'")
    assert "NEW.billing_policy_version IS NULL" in constants["SESSION_GUARD_SQL"]
    assert "ps.billing_policy_version IS NULL" in constants["PRICE_GUARD_SQL"]
    assert constants["down_revision"] == "20260908_03"
