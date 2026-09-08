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
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Lock, get_ident

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

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
            role_id = connection.execute(text("INSERT INTO roles (name) VALUES ('staff') RETURNING id")).scalar_one()
            legacy_zone_id = connection.execute(text("INSERT INTO zones (name,capacity) VALUES ('Legacy migration zone',2) RETURNING id")).scalar_one()
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
            assert session["checkout_quote_hash"] is None
            assert session["checkout_payment_method"] is None
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
            default_site_id = connection.execute(text("SELECT id FROM parking_sites WHERE name='Bãi xe mặc định'")).scalar_one()
            assert connection.execute(text("SELECT site_id FROM zones WHERE id=:id"), {"id": legacy_zone_id}).scalar_one() == default_site_id
            assert tuple(connection.execute(text("SELECT site_id,user_id,role FROM site_memberships")).one()) == (default_site_id, staff_id, "staff")
            for authority_table in ("portal_account_links", "portal_vehicle_ownerships", "portal_session_grants"):
                assert connection.execute(text(f"SELECT count(*) FROM {authority_table}")).scalar_one() == 0

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


def test_postgres_checkout_confirmation_guard_and_legacy_compatibility():
    """Execute the new migration's function, not merely its offline SQL text."""
    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    suffix = uuid.uuid4().hex[:8]
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                role = connection.execute(text("INSERT INTO roles (name) VALUES (:name) RETURNING id"), {"name": "quote_" + suffix}).scalar_one()
                staff = connection.execute(
                    text("INSERT INTO users (role_id, username, password_hash, full_name) VALUES (:role, :name, 'unused', 'Quote Test') RETURNING id"),
                    {"role": role, "name": "quote_" + suffix},
                ).scalar_one()
                vehicle_type = connection.execute(text("INSERT INTO vehicle_types (name) VALUES (:name) RETURNING id"), {"name": "Quote car " + suffix}).scalar_one()
                vehicle = connection.execute(text("INSERT INTO vehicles (license_plate, vehicle_type_id) VALUES (:plate, :type) RETURNING id"), {"plate": "PGQ-" + suffix, "type": vehicle_type}).scalar_one()
                connection.execute(
                    text("INSERT INTO price_configs (vehicle_type_id, ticket_type, price, effective_date) VALUES (:type, 'HOURLY', 10000, '2026-01-01')"),
                    {"type": vehicle_type},
                )
                insert_active = text(
                    "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, status, staff_in_id) "
                    "VALUES (:id, :vehicle, '2026-09-07 10:00:00', 'active', :staff)"
                )
                complete = (
                    "UPDATE parking_sessions SET status = 'completed', check_out_time = '2026-09-07 11:00:00', "
                    "parking_fee = :fee, staff_out_id = :staff, checkout_quote_hash = :digest, "
                    "checkout_payment_method = :method WHERE id = :id"
                )
                for fee, method in ((10000, "cash"), (10000, "transfer"), (0, None)):
                    session = str(uuid.uuid4())
                    values = {"id": session, "vehicle": vehicle, "staff": staff, "fee": fee, "method": method, "digest": "a" * 64}
                    connection.execute(insert_active, values)
                    _expect_database_rejection(connection, complete, values)
                    connection.execute(text("UPDATE parking_sessions SET status = 'checking_out' WHERE id = :id"), values)
                    for bad in (
                        {"digest": "a" * 63}, {"digest": "A" * 64}, {"digest": "g" * 64},
                        {"digest": None, "method": "cash"},
                        {"method": None if fee else "cash"},
                        {"staff": None},
                    ):
                        _expect_database_rejection(connection, complete, {**values, **bad})
                    connection.execute(text(complete), values)
                    for digest, replacement_method in (("b" * 64, method), (None, None)):
                        _expect_database_rejection(
                            connection,
                            "UPDATE parking_sessions SET checkout_quote_hash = :digest, checkout_payment_method = :method WHERE id = :id",
                            {"id": session, "digest": digest, "method": replacement_method},
                        )
                    if fee:
                        connection.execute(text(
                            "INSERT INTO payments (id, source_type, source_id, kind, amount, method, collected_by_id, created_at, idempotency_key) "
                            "VALUES (:payment, 'parking_session', :id, 'receipt', :fee, :method, :staff, '2026-09-07 11:00:00', :key)"
                        ), {**values, "payment": str(uuid.uuid4()), "key": "quote:" + session})

                legacy = {"id": str(uuid.uuid4()), "vehicle": vehicle, "staff": staff, "fee": 10000, "digest": None, "method": None}
                connection.execute(insert_active, legacy)
                connection.execute(text("UPDATE parking_sessions SET status = 'checking_out' WHERE id = :id"), legacy)
                connection.execute(text(complete), legacy)
                _expect_database_rejection(connection, complete, {**legacy, "digest": "a" * 64, "method": "cash"})
                _expect_database_rejection(connection,
                    "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, check_out_time, status, parking_fee, staff_in_id, staff_out_id, checkout_quote_hash, checkout_payment_method) "
                    "VALUES (:id, :vehicle, '2026-09-07 10:00:00', '2026-09-07 11:00:00', 'completed', :fee, :staff, :staff, :digest, :method)",
                    {**legacy, "id": str(uuid.uuid4()), "digest": "a" * 64, "method": "cash"},
                )
                from postgres_readiness import _validate_business_invariants
                _validate_business_invariants(connection)
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


@contextmanager
def _isolated_checkout_postgres():
    """Concurrent commits use a disposable database on the designated CI host."""
    source = make_url(POSTGRES_TEST_URL)
    if not (
        os.getenv("CI", "").lower() in {"true", "1"}
        and source.drivername == "postgresql+psycopg"
        and source.host in {"127.0.0.1", "localhost", "::1"}
        and source.database == source.username == "parkingai_test"
        and not source.query
        and not any(os.getenv(name) for name in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"))
    ):
        pytest.skip("Concurrent commits require the designated loopback CI service")
    name = "parkingai_checkout_" + uuid.uuid4().hex
    temporary = source.set(database=name)
    admin = create_engine(source, isolation_level="AUTOCOMMIT")
    engine = create_engine(temporary, connect_args={"options": "-c lock_timeout=5000 -c statement_timeout=10000"})
    quoted = admin.dialect.identifier_preparer.quote(name)
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f"CREATE DATABASE {quoted} TEMPLATE template0 ENCODING 'UTF8'"))
            created = True
        backend = Path(__file__).resolve().parents[1] / "backend"
        migration_env = {**os.environ, "DATABASE_URL": temporary.render_as_string(hide_password=False)}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), "upgrade", "head"],
            cwd=backend, env=migration_env, capture_output=True, text=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        yield engine
    finally:
        engine.dispose()
        try:
            if created:
                assert name.startswith("parkingai_checkout_") and name != source.database
                assert temporary.database == name
                with admin.connect() as connection:
                    connection.execute(text(f"DROP DATABASE {quoted} WITH (FORCE)"))
        finally:
            admin.dispose()


def test_postgres_parallel_checkouts_same_cashier_do_not_upgrade_fk_locks():
    """Both reach the first cashier lock together, before either may collect.

    Regressing to lock-after-billing gives both transactions FK KEY SHARE on
    the cashier before this barrier, so their FOR UPDATE upgrades deadlock.
    Acquiring the cashier lock first serializes both complete transactions.
    """
    from core.clock import business_now
    from schemas.checkout import CheckoutConfirmation
    from services.checkout_service import CheckoutService

    with _isolated_checkout_postgres() as engine:
        at = business_now()
        session_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        shift_id = str(uuid.uuid4())
        with engine.begin() as connection:
            role = connection.execute(text("INSERT INTO roles (name) VALUES ('staff') RETURNING id")).scalar_one()
            staff = connection.execute(text(
                "INSERT INTO users (role_id, username, password_hash, full_name) "
                "VALUES (:role, 'parallel-cashier', 'unused', 'Parallel Cashier') RETURNING id"
            ), {"role": role}).scalar_one()
            vehicle_type = connection.execute(text("INSERT INTO vehicle_types (name) VALUES ('Parallel car') RETURNING id")).scalar_one()
            connection.execute(text(
                "INSERT INTO price_configs (vehicle_type_id, ticket_type, price, effective_date) "
                "VALUES (:type, 'HOURLY', 10000, :effective)"
            ), {"type": vehicle_type, "effective": (at - timedelta(days=1)).date()})
            connection.execute(text(
                "INSERT INTO cash_shifts (id, staff_id, opened_at, opening_cash, status) "
                "VALUES (:id, :staff, :opened, 100000, 'open')"
            ), {"id": shift_id, "staff": staff, "opened": at - timedelta(hours=4)})
            for index, session_id in enumerate(session_ids):
                vehicle = connection.execute(text(
                    "INSERT INTO vehicles (license_plate, vehicle_type_id) VALUES (:plate, :type) RETURNING id"
                ), {"plate": f"PARALLEL-{index}", "type": vehicle_type}).scalar_one()
                connection.execute(text(
                    "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, status, staff_in_id) "
                    "VALUES (:id, :vehicle, :entry, 'active', :staff)"
                ), {"id": session_id, "vehicle": vehicle, "entry": at - timedelta(hours=2, minutes=15), "staff": staff})
        confirmations = {}
        with Session(engine) as db:
            for session_id in session_ids:
                quote = CheckoutService(db).quote(session_id, staff)
                assert quote["parking_fee"] == 30000
                confirmations[session_id] = CheckoutConfirmation(
                    quote_token=quote["quote_token"], payment_confirmed=True, payment_method="cash",
                )

        barrier, seen, seen_lock = Barrier(2, timeout=10), set(), Lock()

        def before_operator_lock(connection, cursor, statement, parameters, context, executemany):
            sql = " ".join(statement.upper().split())
            if "FROM USERS" not in sql or "FOR UPDATE" not in sql:
                return
            with seen_lock:
                first = get_ident() not in seen
                seen.add(get_ident())
            if first:
                barrier.wait()

        def complete(session_id):
            with Session(engine) as db:
                result = CheckoutService(db).confirm(confirmations[session_id], staff, session_id=session_id)
                return result.id, result.status, result.parking_fee

        event.listen(engine, "before_cursor_execute", before_operator_lock)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(complete, session_id) for session_id in session_ids]
                results = [future.result(timeout=20) for future in futures]
            assert len(seen) == 2
            assert sorted(results) == sorted((session_id, "completed", 30000) for session_id in session_ids)
        finally:
            event.remove(engine, "before_cursor_execute", before_operator_lock)
        with engine.connect() as connection:
            receipts = connection.execute(text(
                "SELECT source_id, amount, collected_by_id, shift_id FROM payments WHERE kind = 'receipt'"
            )).all()
            assert sorted(tuple(row) for row in receipts) == sorted((session_id, 30000, staff, shift_id) for session_id in session_ids)
        check_postgres_readiness(engine, deep=True)


def test_postgres_expansion_commitments_and_demo_ledger_guards():
    """Actual migrated PostgreSQL executes the new guards, not ORM substitutes."""
    from core.clock import business_now
    from expansion.site_models import ParkingSite, ParkingReservation
    from models import Customer, MonthlyPass, ParkingSlot, Payment, Role, User, Vehicle, VehicleType, Zone

    engine = create_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    suffix = uuid.uuid4().hex[:8]
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    role = Role(name="expansion_" + suffix)
                    customer = Customer(full_name="Expansion customer", phone_number="EXP-" + suffix)
                    vehicle_type = VehicleType(name="Expansion car " + suffix)
                    site = ParkingSite(name="Expansion site " + suffix)
                    db.add_all([role, customer, vehicle_type, site])
                    db.flush()
                    staff = User(role_id=role.id, username="expansion_" + suffix, password_hash="unused", full_name="Expansion Staff", is_active=True)
                    vehicle = Vehicle(license_plate="EX-" + suffix, vehicle_type_id=vehicle_type.id, customer_id=customer.id)
                    zone = Zone(name="Expansion zone " + suffix, capacity=2, site_id=site.id, is_active=True)
                    db.add_all([staff, vehicle, zone])
                    db.flush()
                    slot = ParkingSlot(zone_id=zone.id, vehicle_type_id=vehicle_type.id, slot_name="EX-" + suffix, is_active=True, is_occupied=False)
                    db.add(slot)
                    db.flush()
                    start = business_now() + timedelta(days=2)
                    reservation = ParkingReservation(site_id=site.id, slot_id=slot.id, customer_id=customer.id, vehicle_id=vehicle.id,
                                                     start_at=start, end_at=start + timedelta(hours=2), arrival_deadline=start + timedelta(minutes=15),
                                                     request_id=uuid.uuid4().hex, created_by_id=staff.id)
                    real_period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=500000, start_date=date(2027, 1, 1), end_date=date(2027, 1, 31), is_active=True)
                    demo_period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=500000, start_date=date(2027, 2, 1), end_date=date(2027, 2, 28), is_active=True)
                    db.add_all([reservation, real_period, demo_period])
                    db.flush()
                    real_receipt = Payment(source_type="monthly_pass", source_id=str(real_period.id), kind="receipt", amount=500000, method="cash", idempotency_key=uuid.uuid4().hex)
                    demo_receipt = Payment(source_type="monthly_pass", source_id=str(demo_period.id), kind="receipt", amount=500000, method="demo", idempotency_key=uuid.uuid4().hex)
                    db.add_all([real_receipt, demo_receipt])
                    db.flush()
                    values = {"id": reservation.id, "slot": slot.id, "zone": zone.id}
                    _expect_database_rejection(connection, "UPDATE zones SET site_id=NULL WHERE id=:zone", values)
                    _expect_database_rejection(connection, "UPDATE parking_slots SET is_active=false WHERE id=:slot", values)
                    _expect_database_rejection(connection, "UPDATE parking_reservations SET end_at=end_at+INTERVAL '1 hour' WHERE id=:id", values)
                    _expect_database_rejection(connection, """
                        INSERT INTO parking_reservations (id,site_id,slot_id,customer_id,vehicle_id,start_at,end_at,arrival_deadline,status,request_id,created_by_id,created_at)
                        SELECT :new_id,site_id,slot_id,customer_id,vehicle_id,start_at,end_at,arrival_deadline,status,:request_id,created_by_id,created_at
                        FROM parking_reservations WHERE id=:id
                    """, {**values, "new_id": str(uuid.uuid4()), "request_id": uuid.uuid4().hex})
                    refund_sql = """
                        INSERT INTO payments (id,source_type,source_id,kind,amount,method,collected_by_id,shift_id,created_at,idempotency_key,original_payment_id,reason)
                        VALUES (:id,'monthly_pass',:source,'refund',100,:method,NULL,NULL,clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh',:key,:original,'Demo boundary test')
                    """
                    for original, method in ((real_receipt, "demo"), (demo_receipt, "cash")):
                        with pytest.raises(DBAPIError, match="demo payment"):
                            with connection.begin_nested():
                                connection.execute(text(refund_sql), {"id": str(uuid.uuid4()), "source": original.source_id, "method": method, "key": uuid.uuid4().hex, "original": original.id})
                    connection.execute(text(refund_sql), {"id": str(uuid.uuid4()), "source": demo_receipt.source_id, "method": "demo", "key": uuid.uuid4().hex, "original": demo_receipt.id})
                    connection.execute(text("UPDATE parking_reservations SET status='cancelled' WHERE id=:id"), values)
                    connection.execute(text("UPDATE parking_slots SET is_active=false WHERE id=:slot"), values)
                    check_postgres_readiness(engine, deep=True)
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
