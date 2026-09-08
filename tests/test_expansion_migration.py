"""Expansion rollout preserves financial history and does not infer authority."""
import ast
from datetime import date
import hashlib
import io
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from db_rollout import check_database_readiness, initialize_database, migrate_copy
from expansion.site_models import (
    ParkingSite,
    SiteMembership,
    SITE_POSTGRES_GUARD_SQL,
    SITE_SQLITE_GUARDS,
    ZONE_COMMITMENT_POSTGRES_GUARD_SQL,
)
from expansion_rollout import DEFAULT_SITE_NAME, EXPANSION_TABLES
from expansion_demo_guards import DEMO_POSTGRES_GUARD_SQL, DEMO_SQLITE_GUARD_SQL, validate_demo_ledger
from finance_rollout import backfill_legacy_finance
from models import Base
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.role import Role
from models.user import User
from models.zone import Zone
from test_finance_rollout import _seed_legacy_finance


def _make_pre_expansion(path, *, unknown_method=False):
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        _seed_legacy_finance(engine)
        with Session(engine) as db:
            db.add(Zone(name="Legacy zone", capacity=3, is_active=True))
            manager = Role(name="manager")
            db.add(manager)
            db.flush()
            db.add(User(role_id=manager.id, username="legacy_manager", full_name="Manager", password_hash="unused", is_active=True))
            db.commit()
        with engine.begin() as connection:
            backfill_legacy_finance(connection)
        with Session(engine) as db:
            receipt = db.scalar(select(Payment).where(Payment.source_type == "monthly_pass"))
            db.add(Payment(id="legacy-refund", source_type=receipt.source_type, source_id=receipt.source_id,
                           kind="refund", amount=100, method="cash", original_payment_id=receipt.id,
                           reason="Historical refund", idempotency_key="legacy-refund"))
            db.commit()
        raw = engine.raw_connection()
        try:
            raw.execute("PRAGMA foreign_keys=OFF")
            raw.execute("PRAGMA legacy_alter_table=ON")
            for name in SITE_SQLITE_GUARDS:
                raw.execute(f'DROP TRIGGER IF EXISTS "{name}"')
            raw.execute("DROP TRIGGER IF EXISTS trg_payment_demo_boundary")
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in EXPANSION_TABLES:
                    raw.execute(f'DROP TABLE "{table.name}"')
            raw.execute("DROP INDEX ix_zones_site_id")
            zone_objects = raw.execute("SELECT sql FROM sqlite_master WHERE tbl_name='zones' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
            raw.execute("""CREATE TABLE old_zones (
                id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(50) NOT NULL,
                capacity INTEGER NOT NULL, is_active BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            raw.execute("INSERT INTO old_zones SELECT id,name,capacity,is_active,created_at,updated_at FROM zones")
            raw.execute("DROP TABLE zones")
            raw.execute("ALTER TABLE old_zones RENAME TO zones")
            for (statement,) in zone_objects:
                raw.execute(statement)
            ddl = raw.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='payments'").fetchone()[0]
            ddl = ddl.replace("'legacy_unknown', 'demo'", "'legacy_unknown', 'other'" if unknown_method else "'legacy_unknown'")
            ddl = re.sub(r",?\s*CONSTRAINT ck_payment_demo_unassigned CHECK \(method != 'demo' OR shift_id IS NULL\),?", ",", ddl)
            ddl = ddl.replace("CREATE TABLE payments", "CREATE TABLE old_payments")
            objects = raw.execute("SELECT sql FROM sqlite_master WHERE tbl_name='payments' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
            raw.execute(ddl)
            raw.execute("INSERT INTO old_payments SELECT * FROM payments")
            raw.execute("DROP TABLE payments")
            raw.execute("ALTER TABLE old_payments RENAME TO payments")
            for (statement,) in objects:
                raw.execute(statement)
            raw.execute("ALTER TABLE payments ADD COLUMN legacy_note TEXT DEFAULT 'preserved'")
            raw.execute("CREATE INDEX ix_payment_legacy_note ON payments(legacy_note)")
            raw.execute("CREATE TRIGGER legacy_payment_note_guard BEFORE INSERT ON payments WHEN NEW.legacy_note='blocked' BEGIN SELECT RAISE(ABORT,'legacy note rejected'); END")
            raw.execute("CREATE TABLE legacy_receipt_notes (receipt_id TEXT REFERENCES payments(id), note TEXT)")
            raw.execute("INSERT INTO legacy_receipt_notes SELECT id,'receipt reference preserved' FROM payments WHERE kind='receipt'")
            raw.commit()
            history = raw.execute("SELECT * FROM payments ORDER BY id").fetchall()
            assert raw.execute("PRAGMA foreign_key_check").fetchall() == []
            return history
        finally:
            raw.close()
    finally:
        engine.dispose()


def test_legacy_copy_preserves_payment_rows_refunds_custom_schema_and_source(tmp_path):
    source, output = tmp_path / "before.db", tmp_path / "after.db"
    old_rows = _make_pre_expansion(source)
    original = (source.read_bytes(), source.stat().st_mtime_ns)
    migrate_copy(source, output)
    assert (source.read_bytes(), source.stat().st_mtime_ns) == original
    for _ in range(2):
        initialize_database(output)
        engine = create_engine("sqlite:///" + output.as_posix())
        try:
            with engine.connect() as connection:
                assert [tuple(row) for row in connection.exec_driver_sql("SELECT * FROM payments ORDER BY id")] == old_rows
                assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
                assert connection.exec_driver_sql("SELECT COUNT(*) FROM legacy_receipt_notes n JOIN payments p ON p.id=n.receipt_id").scalar_one() == 2
                assert connection.exec_driver_sql("PRAGMA foreign_key_list(legacy_receipt_notes)").one()[2] == "payments"
                assert connection.exec_driver_sql("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('ix_payment_legacy_note','legacy_payment_note_guard')").scalar_one() == 2
                assert connection.exec_driver_sql("SELECT name FROM parking_sites").scalar_one() == DEFAULT_SITE_NAME
                assert connection.exec_driver_sql("SELECT COUNT(*) FROM zones WHERE site_id IS NULL").scalar_one() == 0
                assert set(connection.exec_driver_sql("SELECT role FROM site_memberships").scalars()) == {"staff", "manager"}
                for table in ("portal_account_links", "portal_vehicle_ownerships", "portal_session_grants"):
                    assert connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one() == 0
            check_database_readiness(engine)
        finally:
            engine.dispose()


def test_migrated_ledger_accepts_demo_without_relabeling_actual_receipts(tmp_path):
    source, output = tmp_path / "before.db", tmp_path / "after.db"
    old_rows = _make_pre_expansion(source)
    migrate_copy(source, output)
    engine = create_engine("sqlite:///" + output.as_posix())
    try:
        with Session(engine) as db:
            old_pass = db.scalar(select(MonthlyPass))
            period = MonthlyPass(customer_id=old_pass.customer_id, vehicle_id=old_pass.vehicle_id,
                                 start_date=date(2027, 1, 1), end_date=date(2027, 1, 31), price=300000, is_active=True)
            db.add(period)
            db.flush()
            db.add(Payment(id="demo-receipt", source_type="monthly_pass", source_id=str(period.id),
                           amount=300000, kind="receipt", method="demo", idempotency_key="demo-test"))
            db.commit()
            assert db.get(Payment, "demo-receipt").shift_id is None
        with engine.connect() as connection:
            assert [tuple(row) for row in connection.exec_driver_sql("SELECT * FROM payments WHERE id != 'demo-receipt' ORDER BY id")] == old_rows
        check_database_readiness(engine)
    finally:
        engine.dispose()


def test_unknown_payment_check_refuses_to_publish_or_mutate_source(tmp_path):
    source, output = tmp_path / "unknown.db", tmp_path / "after.db"
    _make_pre_expansion(source, unknown_method=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="ck_payment_method"):
        migrate_copy(source, output)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert not output.exists()


def test_initialization_does_not_grant_new_staff_implicit_membership(tmp_path):
    path = tmp_path / "fresh.db"
    initialize_database(path)
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        with Session(engine) as db:
            role = Role(name="staff")
            db.add(role)
            db.flush()
            db.add(User(username="new_staff", role_id=role.id, full_name="New Staff", password_hash="unused", is_active=True))
            db.commit()
    finally:
        engine.dispose()
    initialize_database(path)
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        with Session(engine) as db:
            assert db.scalars(select(SiteMembership)).all() == []
    finally:
        engine.dispose()


def test_multiple_sites_with_unassigned_zone_refuse_ambiguous_backfill(tmp_path):
    path = tmp_path / "ambiguous.db"
    initialize_database(path)
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        with Session(engine) as db:
            db.add(ParkingSite(name="Second site"))
            db.add(Zone(name="Unknown site", capacity=1, is_active=True))
            db.commit()
    finally:
        engine.dispose()
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="nhiều bãi xe"):
        initialize_database(path)
    assert path.read_bytes() == before


def test_expansion_postgres_revision_is_frozen_and_has_matching_schema(monkeypatch):
    root = Path(__file__).parents[1]
    path = root / "backend/alembic/versions/20260907_02_expansion_demo.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert constants["revision"] == "20260907_02"
    assert constants["down_revision"] == "20260907_01"
    assert constants["SITE_POSTGRES_GUARD_SQL"] == SITE_POSTGRES_GUARD_SQL
    assert constants["SITE_SQLITE_GUARDS"] == SITE_SQLITE_GUARDS
    assert constants["DEMO_POSTGRES_GUARD_SQL"] == DEMO_POSTGRES_GUARD_SQL
    dialect = postgresql.dialect()
    # This snapshot predates the independently migrated scoped AI history table.
    tables = [table for table in Base.metadata.sorted_tables if table.name in EXPANSION_TABLES - {"site_ai_analyses"}]
    assert constants["EXPANSION_TABLE_SQL"] == tuple(str(CreateTable(table).compile(dialect=dialect)).strip() for table in tables)
    indexes = [index for table in tables for index in sorted(table.indexes, key=lambda index: index.name)]
    indexes.extend(index for index in Base.metadata.tables["zones"].indexes if index.name == "ix_zones_site_id")
    assert constants["EXPANSION_INDEX_SQL"] == tuple(str(CreateIndex(index).compile(dialect=dialect)).strip() for index in indexes)
    assert all(not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith(("models", "expansion")) for node in tree.body)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
    buffer = io.StringIO()
    config = Config(str(root / "backend/alembic.ini"), output_buffer=buffer)
    config.set_main_option("script_location", str(root / "backend/alembic"))
    command.upgrade(config, "20260907_01:head", sql=True)
    sql = buffer.getvalue()
    assert "ALTER TABLE payments DROP CONSTRAINT ck_payment_method" in sql
    assert "ck_payment_demo_unassigned" in sql
    assert "FOREIGN KEY(site_id) REFERENCES parking_sites (id)" in sql
    assert "INSERT INTO portal_account_links" not in sql
    assert "UPDATE parking_sessions" not in sql
    assert "DROP TABLE" not in sql
    assert sql.count("CREATE TABLE site_ai_analyses") == 1


def test_zone_commitment_revision_is_additive_and_offline_renderable(monkeypatch):
    root = Path(__file__).parents[1]
    path = root / "backend/alembic/versions/20260908_01_zone_commitment_guard.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert constants["revision"] == "20260908_01"
    assert constants["down_revision"] == "20260907_02"
    assert constants["ZONE_COMMITMENT_POSTGRES_GUARD_SQL"] == ZONE_COMMITMENT_POSTGRES_GUARD_SQL
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
    buffer = io.StringIO()
    config = Config(str(root / "backend/alembic.ini"), output_buffer=buffer)
    config.set_main_option("script_location", str(root / "backend/alembic"))
    command.upgrade(config, "20260907_02:head", sql=True)
    sql = buffer.getvalue()
    assert "CREATE TRIGGER trg_zone_commitment_guard" in sql
    assert "DROP TABLE" not in sql


def test_readiness_rejects_missing_site_guard(tmp_path):
    path = tmp_path / "site.db"
    initialize_database(path)
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER trg_zone_site_immutable")
        with pytest.raises(RuntimeError, match="trg_zone_site_immutable"):
            check_database_readiness(engine)
    finally:
        engine.dispose()


@pytest.mark.parametrize("original,method,source,collector", [
    ("cash", "demo", "monthly_pass", None),
    ("demo", "cash", "monthly_pass", None),
    ("demo", "transfer", "monthly_pass", 1),
    (None, "demo", "parking_session", None),
    (None, "demo", "monthly_pass", 1),
])
def test_demo_boundary_rejects_sql_that_could_mix_actual_and_simulated_money(original, method, source, collector):
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE payments (id TEXT, method TEXT, source_type TEXT, shift_id TEXT, kind TEXT, collected_by_id INTEGER, original_payment_id TEXT)")
            connection.exec_driver_sql(DEMO_SQLITE_GUARD_SQL)
            if original:
                connection.exec_driver_sql("INSERT INTO payments (id,method,source_type,kind) VALUES ('original',?,'monthly_pass','receipt')", (original,))
            with pytest.raises(IntegrityError, match="demo payment"):
                connection.exec_driver_sql("INSERT INTO payments (id,method,source_type,kind,collected_by_id,original_payment_id) VALUES ('new',?,?,?,?,?)", (method, source, "refund" if original else "receipt", collector, "original" if original else None))
            # Readiness also catches a historical direct write made while the
            # guard was missing; accepting schema shape alone is insufficient.
            connection.exec_driver_sql("DROP TRIGGER trg_payment_demo_boundary")
            connection.exec_driver_sql("INSERT INTO payments (id,method,source_type,kind,collected_by_id,original_payment_id) VALUES ('new',?,?,?,?,?)", (method, source, "refund" if original else "receipt", collector, "original" if original else None))
            with pytest.raises(RuntimeError, match="thanh toán demo"):
                validate_demo_ledger(connection)
    finally:
        engine.dispose()
