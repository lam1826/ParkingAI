"""Candidate-only legacy migration and financial-history backstop checks."""

from datetime import date, datetime
from contextlib import closing
import ast
import hashlib
import io
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base
from db_rollout import check_database_readiness, initialize_database, migrate_copy
from finance_rollout import validate_finance_invariants
from models.customer import Customer
from models.cash_shift import SHIFT_POSTGRES_GUARD_SQL
from models.monthly_pass import MonthlyPass
from models.parking_card import ParkingCard
from models.parking_session import ParkingSession
from models.payment import PAYMENT_POSTGRES_GUARD_SQL, PAYMENT_POSTGRES_SOURCE_DELETE_SQL, Payment
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType


def test_legacy_monthly_schema_gets_card_foreign_key_and_unique_renewal_key(tmp_path):
    target = tmp_path / "old-monthly.db"
    with closing(sqlite3.connect(target)) as connection:
        connection.execute("""CREATE TABLE monthly_passes (
            id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
            vehicle_id INTEGER NOT NULL REFERENCES vehicles(id), pass_code VARCHAR(50),
            price INTEGER NOT NULL DEFAULT 0, start_date DATE NOT NULL, end_date DATE NOT NULL,
            is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.commit()

    initialize_database(target)
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        inspector = inspect(engine)
        assert {"card_id", "renewal_key"} <= {column["name"] for column in inspector.get_columns("monthly_passes")}
        assert any(fk["referred_table"] == "parking_cards" and fk["constrained_columns"] == ["card_id"] for fk in inspector.get_foreign_keys("monthly_passes"))
        assert any(index["unique"] and index["column_names"] == ["renewal_key"] for index in inspector.get_indexes("monthly_passes"))
        check_database_readiness(engine)
    finally:
        engine.dispose()


def _seed_legacy_finance(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        role = Role(name="staff")
        vehicle_type = VehicleType(name="Test car", description="Test", is_active=True)
        customer = Customer(full_name="Legacy Customer", phone_number="0900000011")
        db.add_all([role, vehicle_type, customer])
        db.flush()
        user = User(role_id=role.id, username="legacy_staff", password_hash="unused", full_name="Legacy Staff", is_active=True)
        vehicle = Vehicle(license_plate="30A-11111", vehicle_type_id=vehicle_type.id, customer_id=customer.id)
        db.add_all([user, vehicle])
        db.flush()
        period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, pass_code="CARD-LEGACY",
                             price=500_000, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
                             is_active=True, created_at=datetime(2026, 8, 31, 18, 30))
        # A completed historical session does not need a current price table.
        session = ParkingSession(id="legacy-session", vehicle_id=vehicle.id, status="completed",
                                 check_in_time=datetime(2026, 8, 31, 22), check_out_time=datetime(2026, 8, 31, 23),
                                 parking_fee=25_000, staff_in_id=user.id, staff_out_id=user.id)
        db.add_all([period, session])
        db.commit()
        return period.id


def test_copy_backfill_preserves_source_and_is_idempotent_with_business_dates(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "upgraded.db"
    source_engine = create_engine("sqlite:///" + source.as_posix())
    try:
        period_id = _seed_legacy_finance(source_engine)
    finally:
        source_engine.dispose()
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    migrate_copy(source, output)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    engine = create_engine("sqlite:///" + output.as_posix())
    try:
        with Session(engine) as db:
            payments = db.scalars(select(Payment)).all()
            assert len(payments) == 2
            by_source = {payment.source_type: payment for payment in payments}
            assert by_source["monthly_pass"].amount == 500_000
            assert by_source["monthly_pass"].created_at == datetime(2026, 9, 1, 1, 30)
            assert by_source["parking_session"].created_at == datetime(2026, 8, 31, 23)
            assert all(payment.method == "legacy_unknown" and payment.collected_by_id is None and payment.shift_id is None for payment in payments)
            payment_ids = {payment.id for payment in payments}
            period = db.get(MonthlyPass, period_id)
            assert period.pass_code == "CARD-LEGACY" and period.price == 500_000
            assert period.card.code == "CARD-LEGACY"
            assert period.card.customer_id == period.customer_id and period.card.vehicle_id == period.vehicle_id
        check_database_readiness(engine)
    finally:
        engine.dispose()

    initialize_database(output)
    engine = create_engine("sqlite:///" + output.as_posix())
    try:
        with Session(engine) as db:
            assert set(db.scalars(select(Payment.id))) == payment_ids
            assert len(db.scalars(select(ParkingCard)).all()) == 1
    finally:
        engine.dispose()


def test_legacy_session_migration_retains_null_coverage_and_locks_it(tmp_path):
    target = tmp_path / "legacy-coverage.db"
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        _seed_legacy_finance(engine)
        with engine.begin() as connection:
            # Model an actual pre-release table, retaining its historical row.
            connection.exec_driver_sql("DROP TRIGGER trg_parking_sessions_monthly_coverage_insert")
            connection.exec_driver_sql("DROP TRIGGER trg_parking_sessions_monthly_coverage_immutable")
            connection.exec_driver_sql("ALTER TABLE parking_sessions DROP COLUMN monthly_coverage_end")
    finally:
        engine.dispose()
    initialize_database(target)
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        assert any(column["name"] == "monthly_coverage_end" and column["nullable"] for column in inspect(engine).get_columns("parking_sessions"))
        with engine.begin() as connection:
            assert connection.exec_driver_sql("SELECT monthly_coverage_end FROM parking_sessions WHERE id = 'legacy-session'").scalar_one() is None
            with pytest.raises(IntegrityError, match="coverage snapshot immutable"):
                connection.exec_driver_sql("UPDATE parking_sessions SET monthly_coverage_end = '2026-09-30' WHERE id = 'legacy-session'")
        check_database_readiness(engine)
    finally:
        engine.dispose()


@pytest.mark.parametrize("coverage,has_pass", [
    ("2026-10-31", False),
    ("2026-09-05", True),  # Must cover at least the original period's full end.
    ("2026-09-31", True),  # A nonexistent date cannot become a fee entitlement.
    ("invalid", True),
])
def test_coverage_snapshot_rejects_invalid_initial_entitlement(tmp_path, coverage, has_pass):
    engine = create_engine("sqlite:///" + (tmp_path / "invalid-coverage.db").as_posix())
    try:
        period_id = _seed_legacy_finance(engine)
        with engine.begin() as connection:
            with pytest.raises(IntegrityError, match="monthly coverage snapshot invalid"):
                connection.execute(text(
                    "INSERT INTO parking_sessions (id, vehicle_id, monthly_pass_id, monthly_coverage_end, check_in_time, check_out_time, parking_fee, status, staff_in_id, staff_out_id) "
                    "VALUES ('coverage-invalid', 1, :pass_id, :coverage, '2026-09-01 10:00:00', '2026-09-01 11:00:00', 0, 'completed', 1, 1)"
                ), {"pass_id": period_id if has_pass else None, "coverage": coverage})
    finally:
        engine.dispose()


def test_conflicting_legacy_card_owner_leaves_original_database_unchanged(tmp_path):
    target = tmp_path / "conflicting-card.db"
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        period_id = _seed_legacy_finance(engine)
        with Session(engine) as db:
            period = db.get(MonthlyPass, period_id)
            other = Customer(full_name="Other Owner", phone_number="0900000012")
            db.add(other)
            db.flush()
            db.add(ParkingCard(code=period.pass_code, customer_id=other.id, vehicle_id=period.vehicle_id))
            db.commit()
    finally:
        engine.dispose()
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError, match="conflicts with its physical card owner"):
        initialize_database(target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("mutation", [
    "UPDATE monthly_passes SET price = 1 WHERE id = :id",
    "UPDATE monthly_passes SET end_date = '2026-10-01' WHERE id = :id",
    "UPDATE monthly_passes SET card_id = NULL WHERE id = :id",
    "DELETE FROM monthly_passes WHERE id = :id",
    "UPDATE parking_cards SET code = 'CHANGED' WHERE id = (SELECT card_id FROM monthly_passes WHERE id = :id)",
])
def test_imported_paid_period_and_card_identity_are_immutable(tmp_path, mutation):
    target = tmp_path / "history.db"
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        period_id = _seed_legacy_finance(engine)
    finally:
        engine.dispose()
    initialize_database(target)
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        with engine.begin() as connection:
            with pytest.raises(IntegrityError, match="immutable"):
                connection.execute(text(mutation), {"id": period_id})
            # Operational deactivation never destroys historical entitlement.
            connection.execute(text("UPDATE monthly_passes SET is_active = 0 WHERE id = :id"), {"id": period_id})
    finally:
        engine.dispose()


def test_new_postgres_revision_compiles_offline_without_database_access(monkeypatch):
    backend = Path(__file__).parents[1] / "backend"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@example.invalid/unused")
    output = io.StringIO()
    config = Config(str(backend / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(config, "20260828_01:head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE parking_cards" in sql
    assert "CREATE TABLE payments" in sql and "CREATE TABLE cash_shifts" in sql
    assert "fk_monthly_passes_card" in sql and "uq_monthly_passes_renewal_key" in sql
    assert "ADD COLUMN monthly_coverage_end DATE" in sql and "trg_monthly_coverage_guard" in sql
    assert "trim(reason) != ''" in sql
    assert "legacy_unknown" in sql and "AT TIME ZONE 'Asia/Ho_Chi_Minh'" in sql
    assert "trg_payment_guard" in sql and "trg_monthly_finance_guard" in sql
    assert "20260906_01" in sql


def test_postgres_release_migration_installs_current_financial_guard_contracts():
    # A model-only fix must not silently leave the Alembic-managed production
    # schema behind the create_all schema exercised by the ordinary test suite.
    migration = Path(__file__).parents[1] / "backend/alembic/versions/20260906_01_cards_cash_ledger.py"
    definitions = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(migration.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("GUARD_SQL")
    }
    assert definitions["PAYMENT_GUARD_SQL"] == PAYMENT_POSTGRES_GUARD_SQL.replace("%%", "%")
    assert definitions["SHIFT_GUARD_SQL"] == SHIFT_POSTGRES_GUARD_SQL.replace("%%", "%")
    assert definitions["SOURCE_DELETE_GUARD_SQL"] == PAYMENT_POSTGRES_SOURCE_DELETE_SQL.replace("%%", "%")


def test_deep_readiness_detects_orphaned_financial_source(tmp_path):
    target = tmp_path / "orphan.db"
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        _seed_legacy_finance(engine)
    finally:
        engine.dispose()
    initialize_database(target)
    engine = create_engine("sqlite:///" + target.as_posix())
    try:
        with engine.begin() as connection:
            # Simulate a pre-existing damaged/imported database, bypassing its
            # write guards explicitly only inside this disposable test file.
            names = connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'payments'").scalars().all()
            for name in names:
                connection.exec_driver_sql('DROP TRIGGER "' + name.replace('"', '""') + '"')
            connection.exec_driver_sql("UPDATE payments SET source_id = 'missing-source' WHERE source_type = 'parking_session'")
            with pytest.raises(RuntimeError, match="phiếu thu/nguồn thu"):
                validate_finance_invariants(connection)
    finally:
        engine.dispose()
