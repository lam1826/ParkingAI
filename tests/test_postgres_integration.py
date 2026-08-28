"""PostgreSQL-only migration/invariant smoke tests.

The normal local suite skips this file. CI supplies ``POSTGRES_TEST_URL`` and
runs Alembic immediately before this module, using an isolated PostgreSQL
service container rather than any developer or production database.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
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
                    "check_in_time, status, staff_in_id) "
                    "VALUES (:id, :vehicle, :slot, :pass_id, :check_in, "
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
