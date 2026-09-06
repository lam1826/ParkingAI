"""PostgreSQL-only migration/invariant smoke tests.

The normal local suite skips this file. CI supplies ``POSTGRES_TEST_URL`` and
runs Alembic immediately before this module, using an isolated PostgreSQL
service container rather than any developer or production database.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from core.money import MAX_EXACT_VND
from postgres_readiness import POSTGRES_SCHEMA_REVISION, check_postgres_readiness


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="POSTGRES_TEST_URL is only provided by the isolated CI service",
)


def _expect_database_rejection(connection, sql: str, parameters: dict) -> None:
    with pytest.raises(DBAPIError):
        with connection.begin_nested():
            connection.execute(text(sql), parameters)


def test_postgres_cash_ledger_and_paid_period_backstops():
    """CI runs these real PostgreSQL triggers after upgrading the full chain."""
    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    suffix = uuid.uuid4().hex[:8]
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                role = connection.execute(text("INSERT INTO roles (name) VALUES (:name) RETURNING id"), {"name": "finance_" + suffix}).scalar_one()
                staff = connection.execute(text("INSERT INTO users (role_id, username, password_hash, full_name) VALUES (:role, :name, 'unused', 'Finance Test') RETURNING id"), {"role": role, "name": "finance_" + suffix}).scalar_one()
                customer = connection.execute(text("INSERT INTO customers (full_name, phone_number) VALUES ('Finance Customer', :phone) RETURNING id"), {"phone": "PGF-" + suffix}).scalar_one()
                vehicle_type = connection.execute(text("INSERT INTO vehicle_types (name) VALUES (:name) RETURNING id"), {"name": "Finance car " + suffix}).scalar_one()
                vehicle = connection.execute(text("INSERT INTO vehicles (license_plate, vehicle_type_id) VALUES (:plate, :type) RETURNING id"), {"plate": "PGF-" + suffix, "type": vehicle_type}).scalar_one()
                card = connection.execute(text("INSERT INTO parking_cards (code, customer_id, vehicle_id) VALUES (:code, :customer, :vehicle) RETURNING id"), {"code": "CARD-" + suffix, "customer": customer, "vehicle": vehicle}).scalar_one()
                period = connection.execute(text("INSERT INTO monthly_passes (customer_id, vehicle_id, card_id, pass_code, price, start_date, end_date) VALUES (:customer, :vehicle, :card, :code, 500000, '2026-09-01', '2026-09-30') RETURNING id"), {"customer": customer, "vehicle": vehicle, "card": card, "code": "PERIOD-" + suffix}).scalar_one()
                shift = str(uuid.uuid4())
                connection.execute(text("INSERT INTO cash_shifts (id, staff_id, opened_at, opening_cash, status) VALUES (:id, :staff, '2026-09-01 09:00:00', 100000, 'open')"), {"id": shift, "staff": staff})
                payment = str(uuid.uuid4())
                payment_values = {"id": payment, "source": str(period), "staff": staff, "shift": shift, "key": "pg-receipt:" + suffix}
                receipt_sql = "INSERT INTO payments (id, source_type, source_id, kind, amount, method, collected_by_id, shift_id, created_at, idempotency_key) VALUES (:id, 'monthly_pass', :source, 'receipt', 500000, 'cash', :staff, :shift, '2026-09-01 10:00:00', :key)"
                connection.execute(text(receipt_sql), payment_values)
                _expect_database_rejection(connection, receipt_sql, {**payment_values, "id": str(uuid.uuid4()), "key": "duplicate:" + suffix})
                _expect_database_rejection(connection, "UPDATE payments SET amount = 1 WHERE id = :id", {"id": payment})
                _expect_database_rejection(connection, "UPDATE monthly_passes SET price = 1 WHERE id = :id", {"id": period})
                _expect_database_rejection(connection, "DELETE FROM monthly_passes WHERE id = :id", {"id": period})
                _expect_database_rejection(connection, "UPDATE parking_cards SET code = 'CHANGED' WHERE id = :id", {"id": card})
                refund_sql = "INSERT INTO payments (id, source_type, source_id, kind, amount, method, collected_by_id, shift_id, created_at, idempotency_key, original_payment_id, reason) VALUES (:id, 'monthly_pass', :source, 'refund', :amount, 'cash', :staff, :shift, '2026-09-01 11:00:00', :key, :original, 'Refund test')"
                refund_values = {**payment_values, "id": str(uuid.uuid4()), "key": "refund:" + suffix, "original": payment, "amount": 600000}
                _expect_database_rejection(connection, refund_sql, refund_values)
                connection.execute(text(refund_sql), {**refund_values, "amount": 100000})
                close_sql = "UPDATE cash_shifts SET status = 'closed', closed_at = '2026-09-01 12:00:00', counted_cash = :expected, expected_cash = :expected, difference = 0 WHERE id = :id"
                _expect_database_rejection(connection, close_sql, {"expected": 0, "id": shift})
                connection.execute(text(close_sql), {"expected": 500000, "id": shift})
                _expect_database_rejection(connection, "UPDATE cash_shifts SET counted_cash = 1 WHERE id = :id", {"id": shift})
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_postgres_baseline_and_concurrency_backstops():
    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    try:
        check_postgres_readiness(engine, deep=True)
        connection = engine.connect()
        transaction = connection.begin()
        try:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            assert revision == POSTGRES_SCHEMA_REVISION

            role_id = connection.execute(
                text("INSERT INTO roles (name) VALUES ('pg_staff') RETURNING id")
            ).scalar_one()
            type_id = connection.execute(
                text(
                    "INSERT INTO vehicle_types (name) "
                    "VALUES ('Ô tô PostgreSQL') RETURNING id"
                )
            ).scalar_one()
            _expect_database_rejection(
                connection,
                "INSERT INTO vehicle_types (name) VALUES (:name)",
                {"name": "  ô TÔ postgresql  "},
            )

            zone_id = connection.execute(
                text(
                    "INSERT INTO zones (name, capacity) "
                    "VALUES ('PG Zone', 1) RETURNING id"
                )
            ).scalar_one()
            user_id = connection.execute(
                text(
                    "INSERT INTO users "
                    "(role_id, username, password_hash, full_name) "
                    "VALUES (:role, 'pg_user', 'not-a-real-hash', 'PG User') "
                    "RETURNING id"
                ),
                {"role": role_id},
            ).scalar_one()
            slot_id = connection.execute(
                text(
                    "INSERT INTO parking_slots "
                    "(zone_id, vehicle_type_id, slot_name) "
                    "VALUES (:zone, :type, 'PG-01') RETURNING id"
                ),
                {"zone": zone_id, "type": type_id},
            ).scalar_one()
            _expect_database_rejection(
                connection,
                "INSERT INTO parking_slots "
                "(zone_id, vehicle_type_id, slot_name) "
                "VALUES (:zone, :type, 'PG-02')",
                {"zone": zone_id, "type": type_id},
            )

            customer_id = connection.execute(
                text(
                    "INSERT INTO customers (full_name, phone_number) "
                    "VALUES ('PG Customer', '0900000099') RETURNING id"
                )
            ).scalar_one()
            vehicle_id = connection.execute(
                text(
                    "INSERT INTO vehicles "
                    "(license_plate, vehicle_type_id, customer_id) "
                    "VALUES ('PG-99', :type, :customer) RETURNING id"
                ),
                {"type": type_id, "customer": customer_id},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO price_configs "
                    "(vehicle_type_id, ticket_type, price, effective_date) "
                    "VALUES (:type, 'HOURLY', :price, :today)"
                ),
                {
                    "type": type_id,
                    "price": MAX_EXACT_VND,
                    "today": date(2026, 8, 28),
                },
            )

            pass_id = connection.execute(
                text(
                    "INSERT INTO monthly_passes "
                    "(customer_id, vehicle_id, pass_code, price, start_date, end_date) "
                    "VALUES (:customer, :vehicle, 'PG-PASS-1', 500000, :start, :end) "
                    "RETURNING id"
                ),
                {
                    "customer": customer_id,
                    "vehicle": vehicle_id,
                    "start": date(2026, 8, 1),
                    "end": date(2026, 8, 31),
                },
            ).scalar_one()
            _expect_database_rejection(
                connection,
                "INSERT INTO monthly_passes "
                "(customer_id, vehicle_id, pass_code, price, start_date, end_date) "
                "VALUES (:customer, :vehicle, 'PG-PASS-2', 500000, :start, :end)",
                {
                    "customer": customer_id,
                    "vehicle": vehicle_id,
                    "start": date(2026, 8, 31),
                    "end": date(2026, 9, 30),
                },
            )

            check_in = datetime(2026, 8, 28, 9, 0, 0)
            session_id = str(uuid.uuid4())
            connection.execute(
                text(
                    "INSERT INTO parking_sessions "
                    "(id, vehicle_id, parking_slot_id, monthly_pass_id, "
                    "monthly_coverage_end, check_in_time, status, staff_in_id) "
                    "VALUES (:id, :vehicle, :slot, :pass_id, '2026-08-31', :check_in, "
                    "'active', :staff)"
                ),
                {
                    "id": session_id,
                    "vehicle": vehicle_id,
                    "slot": slot_id,
                    "pass_id": pass_id,
                    "check_in": check_in,
                    "staff": user_id,
                },
            )
            _expect_database_rejection(
                connection,
                "UPDATE parking_sessions SET monthly_coverage_end = '2026-09-30' WHERE id = :id",
                {"id": session_id},
            )
            _expect_database_rejection(
                connection,
                "UPDATE parking_sessions SET monthly_coverage_end = NULL WHERE id = :id",
                {"id": session_id},
            )
            _expect_database_rejection(
                connection,
                "INSERT INTO parking_sessions "
                "(id, vehicle_id, check_in_time, status, staff_in_id) "
                "VALUES (:id, :vehicle, :check_in, 'active', :staff)",
                {
                    "id": str(uuid.uuid4()),
                    "vehicle": vehicle_id,
                    "check_in": check_in + timedelta(minutes=1),
                    "staff": user_id,
                },
            )

            # Entitlement is captured at admission. Deactivation after
            # check-in must not strand an active vehicle in the car park.
            connection.execute(
                text("UPDATE monthly_passes SET is_active = false WHERE id = :id"),
                {"id": pass_id},
            )
            connection.execute(
                text(
                    "UPDATE parking_sessions SET status = 'checking_out' "
                    "WHERE id = :id"
                ),
                {"id": session_id},
            )
            connection.execute(
                text(
                    "UPDATE parking_sessions "
                    "SET status = 'completed', check_out_time = :check_out, "
                    "parking_fee = 0, staff_out_id = :staff WHERE id = :id"
                ),
                {
                    "id": session_id,
                    "check_out": check_in + timedelta(hours=1),
                    "staff": user_id,
                },
            )
        finally:
            transaction.rollback()
            connection.close()

        # Rollback restores the isolated database to its empty, ready state.
        check_postgres_readiness(engine, deep=True)
    finally:
        engine.dispose()


def test_postgres_populated_legacy_migration_preserves_history():
    """Exercise backfill in a disposable database, never in the supplied DB."""
    source_url = make_url(POSTGRES_TEST_URL)
    if not (
        os.getenv("CI", "").lower() in {"true", "1"}
        and source_url.drivername == "postgresql+psycopg"
        and source_url.host in {"127.0.0.1", "localhost", "::1"}
        and source_url.database == "parkingai_test"
        and source_url.username == "parkingai_test"
        and not source_url.query
        and not any(os.getenv(name) for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"))
    ):
        pytest.skip("Database creation is restricted to the designated loopback CI service")

    database_name = "parkingai_migration_" + uuid.uuid4().hex
    temporary_url = source_url.set(database=database_name)
    admin_engine = create_engine(source_url, isolation_level="AUTOCOMMIT")
    temporary_engine = create_engine(temporary_url)
    quoted_database = admin_engine.dialect.identifier_preparer.quote(database_name)
    backend = Path(__file__).resolve().parents[1] / "backend"
    migration_env = os.environ.copy()
    migration_env["DATABASE_URL"] = temporary_url.render_as_string(hide_password=False)
    created = False

    def upgrade(revision: str) -> None:
        # conftest forces the in-process application to SQLite. A fresh process
        # and explicit URL ensure every migration uses only our disposable DB.
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), "upgrade", revision],
            cwd=backend,
            env=migration_env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {quoted_database} TEMPLATE template0 ENCODING 'UTF8'"))
            created = True

        upgrade("20260828_01")
        session_id = str(uuid.uuid4())
        metadata_utc = datetime(2026, 8, 31, 18, 30)
        check_in = datetime(2026, 9, 30, 23, 30)
        check_out = datetime(2026, 10, 1, 0, 30)
        with temporary_engine.begin() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260828_01"
            role_id = connection.execute(text("INSERT INTO roles (name) VALUES ('legacy_staff') RETURNING id")).scalar_one()
            staff_id = connection.execute(
                text("INSERT INTO users (role_id, username, password_hash, full_name) VALUES (:role, 'legacy_staff', 'unused', 'Legacy Staff') RETURNING id"),
                {"role": role_id},
            ).scalar_one()
            customer_id = connection.execute(text("INSERT INTO customers (full_name, phone_number) VALUES ('Legacy Customer', '0900000001') RETURNING id")).scalar_one()
            type_id = connection.execute(text("INSERT INTO vehicle_types (name) VALUES ('Legacy car') RETURNING id")).scalar_one()
            vehicle_id = connection.execute(
                text("INSERT INTO vehicles (license_plate, vehicle_type_id, customer_id) VALUES ('LEGACY-01', :type, :customer) RETURNING id"),
                {"type": type_id, "customer": customer_id},
            ).scalar_one()
            connection.execute(
                text("INSERT INTO price_configs (vehicle_type_id, ticket_type, price, effective_date) VALUES (:type, 'HOURLY', 25000, '2026-01-01')"),
                {"type": type_id},
            )
            pass_id = connection.execute(
                text("INSERT INTO monthly_passes (customer_id, vehicle_id, pass_code, price, start_date, end_date, created_at, updated_at) VALUES (:customer, :vehicle, 'LEGACY-CARD-01', 500000, '2026-09-01', '2026-09-30', :created, :created) RETURNING id"),
                {"customer": customer_id, "vehicle": vehicle_id, "created": metadata_utc},
            ).scalar_one()
            # The pass covered admission, but checkout followed its expiry.
            connection.execute(
                text("INSERT INTO parking_sessions (id, vehicle_id, monthly_pass_id, check_in_time, check_out_time, parking_fee, status, staff_in_id, staff_out_id) VALUES (:id, :vehicle, :period, :entry, :exit, 25000, 'completed', :staff, :staff)"),
                {"id": session_id, "vehicle": vehicle_id, "period": pass_id, "entry": check_in, "exit": check_out, "staff": staff_id},
            )

        upgrade("head")
        with temporary_engine.connect() as connection:
            period = connection.execute(text("SELECT * FROM monthly_passes")).mappings().one()
            card = connection.execute(text("SELECT * FROM parking_cards")).mappings().one()
            session = connection.execute(text("SELECT * FROM parking_sessions")).mappings().one()
            receipts = [dict(row) for row in connection.execute(text("SELECT * FROM payments ORDER BY source_type")).mappings()]
            assert period["id"] == pass_id
            assert period["pass_code"] == card["code"] == "LEGACY-CARD-01"
            assert period["card_id"] == card["id"]
            assert period["customer_id"] == card["customer_id"] == customer_id
            assert period["vehicle_id"] == card["vehicle_id"] == vehicle_id
            assert period["price"] == 500000
            assert period["start_date"] == date(2026, 9, 1)
            assert period["end_date"] == date(2026, 9, 30)
            assert period["created_at"] == card["created_at"] == metadata_utc
            assert session["id"] == session_id
            assert session["monthly_pass_id"] == pass_id
            assert session["vehicle_id"] == vehicle_id
            assert session["check_in_time"] == check_in
            assert session["check_out_time"] == check_out
            assert session["parking_fee"] == 25000
            assert session["status"] == "completed"
            assert session["monthly_coverage_end"] is None
            assert len(receipts) == 2
            expected = {
                "monthly_pass": (str(pass_id), 500000, datetime(2026, 9, 1, 1, 30)),
                "parking_session": (session_id, 25000, check_out),
            }
            for receipt in receipts:
                source_id, amount, timestamp = expected[receipt["source_type"]]
                assert receipt["source_id"] == source_id
                assert receipt["kind"] == "receipt"
                assert receipt["amount"] == amount
                assert receipt["method"] == "legacy_unknown"
                assert receipt["created_at"] == timestamp
                assert receipt["idempotency_key"] == f"receipt:{receipt['source_type']}:{source_id}"
                assert receipt["collected_by_id"] is None
                assert receipt["shift_id"] is None
                assert receipt["original_payment_id"] is None
            assert connection.execute(text("SELECT count(*) FROM cash_shifts")).scalar_one() == 0

        check_postgres_readiness(temporary_engine, deep=True)
        upgrade("head")
        with temporary_engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == POSTGRES_SCHEMA_REVISION
            assert [dict(row) for row in connection.execute(text("SELECT * FROM payments ORDER BY source_type")).mappings()] == receipts
            assert dict(connection.execute(text("SELECT * FROM parking_cards")).mappings().one()) == dict(card)
            assert dict(connection.execute(text("SELECT * FROM monthly_passes")).mappings().one()) == dict(period)
            assert dict(connection.execute(text("SELECT * FROM parking_sessions")).mappings().one()) == dict(session)
        check_postgres_readiness(temporary_engine, deep=True)
    finally:
        temporary_engine.dispose()
        try:
            if created:
                # Never drop the source DB, nor a name whose CREATE failed.
                assert database_name.startswith("parkingai_migration_")
                assert database_name != source_url.database
                assert temporary_url.database == database_name
                with admin_engine.connect() as connection:
                    connection.execute(text(f"DROP DATABASE {quoted_database} WITH (FORCE)"))
        finally:
            admin_engine.dispose()
