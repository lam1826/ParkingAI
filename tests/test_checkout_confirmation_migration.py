"""Confirmation history survives additive rollout and cannot be forged later."""

import ast
import hashlib
import io
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

import database
from db_rollout import check_database_readiness, initialize_database, migrate_copy
from test_finance_rollout import _seed_legacy_finance


CONFIRMATION_COLUMNS = {"checkout_quote_hash", "checkout_payment_method"}


@pytest.fixture
def confirmation_connection():
    """Isolate the new guards from unrelated admission/fee trigger failures."""
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE parking_sessions (id TEXT PRIMARY KEY, status TEXT, "
                "parking_fee INTEGER, staff_out_id INTEGER, "
                "checkout_quote_hash VARCHAR(64), checkout_payment_method VARCHAR(8))"
            )
            connection.exec_driver_sql(database.CHECKOUT_CONFIRMATION_INSERT_TRIGGER_SQL)
            connection.exec_driver_sql(database.CHECKOUT_CONFIRMATION_UPDATE_TRIGGER_SQL)
            connection.exec_driver_sql("INSERT INTO parking_sessions (id, status) VALUES ('new', 'checking_out')")
            yield connection
    finally:
        engine.dispose()


@pytest.mark.parametrize("digest,method,fee,staff,status", [
    ("a" * 63, "cash", 10000, 1, "completed"),
    ("a" * 65, "cash", 10000, 1, "completed"),
    ("A" * 64, "cash", 10000, 1, "completed"),
    ("g" * 64, "cash", 10000, 1, "completed"),
    ("a" * 64 + "\x00", "cash", 10000, 1, "completed"),
    (b"a" * 64, "cash", 10000, 1, "completed"),
    ("a" * 64, None, 10000, 1, "completed"),
    (None, "cash", 10000, 1, "completed"),
    ("a" * 64, "legacy_unknown", 10000, 1, "completed"),
    ("a" * 64, "cash", 0, 1, "completed"),
    ("a" * 64, None, None, 1, "completed"),
    ("a" * 64, None, -1, 1, "completed"),
    ("a" * 64, "cash", 10000, None, "completed"),
    ("a" * 64, "cash", 10000, 1, "active"),
    ("a" * 64, "cash", 10000, 1, None),
])
def test_confirmation_guard_rejects_invalid_or_incomplete_record(
    confirmation_connection, digest, method, fee, staff, status,
):
    with pytest.raises(IntegrityError, match="checkout confirmation"):
        confirmation_connection.exec_driver_sql(
            "UPDATE parking_sessions SET status = ?, parking_fee = ?, staff_out_id = ?, "
            "checkout_quote_hash = ?, checkout_payment_method = ? WHERE id = 'new'",
            (status, fee, staff, digest, method),
        )
    assert confirmation_connection.exec_driver_sql("SELECT status FROM parking_sessions").scalar_one() == "checking_out"


@pytest.mark.parametrize("fee,method", [(10000, "cash"), (10000, "transfer"), (0, None)])
def test_valid_confirmation_is_only_written_once_at_completion(confirmation_connection, fee, method):
    connection = confirmation_connection
    connection.exec_driver_sql(
        "UPDATE parking_sessions SET status = 'completed', parking_fee = ?, staff_out_id = 1, "
        "checkout_quote_hash = ?, checkout_payment_method = ? WHERE id = 'new'",
        (fee, "a" * 64, method),
    )
    connection.exec_driver_sql("UPDATE parking_sessions SET status = 'completed' WHERE id = 'new'")
    for digest, replacement_method in [("b" * 64, method), (None, None), ("a" * 64, "transfer" if method != "transfer" else "cash")]:
        with pytest.raises(IntegrityError, match="checkout confirmation"):
            connection.exec_driver_sql(
                "UPDATE parking_sessions SET checkout_quote_hash = ?, checkout_payment_method = ? WHERE id = 'new'",
                (digest, replacement_method),
            )


def test_insert_and_unclaimed_completion_cannot_forge_confirmation(confirmation_connection):
    connection = confirmation_connection
    with pytest.raises(IntegrityError, match="checkout confirmation"):
        connection.exec_driver_sql(
            "INSERT INTO parking_sessions (id, status, parking_fee, staff_out_id, checkout_quote_hash, checkout_payment_method) "
            "VALUES ('forged', 'completed', 10000, 1, ?, 'cash')", ("a" * 64,),
        )
    connection.exec_driver_sql("UPDATE parking_sessions SET status = 'active' WHERE id = 'new'")
    with pytest.raises(IntegrityError, match="checkout confirmation"):
        connection.exec_driver_sql(
            "UPDATE parking_sessions SET status = 'completed', parking_fee = 10000, staff_out_id = 1, "
            "checkout_quote_hash = ?, checkout_payment_method = 'cash' WHERE id = 'new'", ("a" * 64,),
        )
    # The previous backend can still complete with no confirmation metadata
    # during rolling deployment or image rollback.
    connection.exec_driver_sql(
        "UPDATE parking_sessions SET status = 'completed', parking_fee = 10000, staff_out_id = 1 WHERE id = 'new'"
    )


def _legacy_database(path):
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        _seed_legacy_finance(engine)
        with engine.begin() as connection:
            triggers = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND name LIKE 'trg_parking_sessions_checkout_confirmation_%'"
            ).scalars().all()
            for name in triggers:
                connection.exec_driver_sql(f'DROP TRIGGER "{name}"')
            existing = {column["name"] for column in inspect(connection).get_columns("parking_sessions")}
            for name in sorted(CONFIRMATION_COLUMNS & existing):
                connection.exec_driver_sql(f"ALTER TABLE parking_sessions DROP COLUMN {name}")
    finally:
        engine.dispose()


def test_legacy_rollout_adds_nullable_columns_without_fabricating_confirmation(tmp_path):
    source, output = tmp_path / "old.db", tmp_path / "new.db"
    _legacy_database(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    migrate_copy(source, output)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    for _ in range(2):
        initialize_database(output)
        engine = create_engine("sqlite:///" + output.as_posix())
        try:
            columns = {column["name"]: column for column in inspect(engine).get_columns("parking_sessions")}
            assert CONFIRMATION_COLUMNS <= columns.keys()
            assert all(columns[name]["nullable"] for name in CONFIRMATION_COLUMNS)
            with engine.connect() as connection:
                row = connection.exec_driver_sql(
                    "SELECT status, parking_fee, checkout_quote_hash, checkout_payment_method "
                    "FROM parking_sessions WHERE id = 'legacy-session'"
                ).one()
                assert tuple(row) == ("completed", 25000, None, None)
            check_database_readiness(engine)
        finally:
            engine.dispose()


def test_legacy_completed_session_cannot_acquire_a_fake_confirmation(tmp_path):
    path = tmp_path / "legacy.db"
    _legacy_database(path)
    initialize_database(path)
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        with engine.begin() as connection:
            with pytest.raises(IntegrityError, match="checkout confirmation"):
                connection.exec_driver_sql(
                    "UPDATE parking_sessions SET checkout_quote_hash = ?, "
                    "checkout_payment_method = 'cash' WHERE id = 'legacy-session'",
                    ("a" * 64,),
                )
    finally:
        engine.dispose()


def test_rollout_refuses_corrupted_confirmation_without_mutating_source(tmp_path):
    path = tmp_path / "corrupted.db"
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        _seed_legacy_finance(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS {database.TRG_CHECKOUT_CONFIRMATION_UPDATE}")
            connection.exec_driver_sql("UPDATE parking_sessions SET checkout_payment_method = 'cash'")
    finally:
        engine.dispose()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="checkout confirmation"):
        initialize_database(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("fee,method", [(0, None), (10000, "cash")])
def test_rollout_never_backfills_legacy_receipts_for_explicit_confirmations(tmp_path, fee, method):
    path = tmp_path / "free.db"
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        _seed_legacy_finance(engine)
        with engine.begin() as connection:
            # Valid non-monthly, no-slot admission using its real source rows.
            connection.exec_driver_sql(
                "INSERT INTO price_configs (vehicle_type_id, ticket_type, price, effective_date, is_active) "
                    "SELECT vehicle_type_id, 'HOURLY', 10000, '2026-08-01', 1 FROM vehicles LIMIT 1"
            )
            connection.exec_driver_sql(
                "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, status, staff_in_id) "
                "SELECT 'free-session', vehicle_id, '2026-08-31 22:00:00', 'active', staff_in_id "
                "FROM parking_sessions WHERE id = 'legacy-session'"
            )
            connection.exec_driver_sql("UPDATE parking_sessions SET status = 'checking_out' WHERE id = 'free-session'")
            connection.exec_driver_sql(
                "UPDATE parking_sessions SET status = 'completed', parking_fee = ?, "
                "staff_out_id = staff_in_id, check_out_time = '2026-08-31 23:00:00', checkout_quote_hash = ?, "
                "checkout_payment_method = ? WHERE id = 'free-session'", (fee, "a" * 64, method),
            )
    finally:
        engine.dispose()
    if fee:
        # A missing real receipt is corruption, not a legacy record to infer.
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with pytest.raises(RuntimeError, match="checkout confirmation"):
            initialize_database(path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        return
    for _ in range(2):
        initialize_database(path)
        engine = create_engine("sqlite:///" + path.as_posix())
        try:
            with engine.connect() as connection:
                assert connection.exec_driver_sql(
                    "SELECT COUNT(*) FROM payments WHERE source_type = 'parking_session' AND source_id = 'free-session'"
                ).scalar_one() == 0
            check_database_readiness(engine)
        finally:
            engine.dispose()


def test_postgres_confirmation_revision_is_additive_and_frozen(monkeypatch):
    root = Path(__file__).parents[1]
    migration = root / "backend/alembic/versions/20260907_01_checkout_confirmation.py"
    assert migration.exists()
    tree = ast.parse(migration.read_text(encoding="utf-8"))
    values = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert values["down_revision"] == "20260906_01"
    assert values["CHECKOUT_CONFIRMATION_POSTGRES_GUARD_SQL"] == database.CHECKOUT_CONFIRMATION_POSTGRES_GUARD_SQL
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
    buffer = io.StringIO()
    config = Config(str(root / "backend/alembic.ini"), output_buffer=buffer)
    config.set_main_option("script_location", str(root / "backend/alembic"))
    command.upgrade(config, "20260906_01:head", sql=True)
    sql = buffer.getvalue()
    assert "ADD COLUMN checkout_quote_hash VARCHAR(64)" in sql
    assert "ADD COLUMN checkout_payment_method VARCHAR(8)" in sql
    assert "trg_parking_sessions_checkout_confirmation_guard" in sql
    assert "UPDATE parking_sessions" not in sql
    assert "DROP COLUMN" not in sql
