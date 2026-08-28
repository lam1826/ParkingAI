import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from crud import parking_session as crud_parking_session
from database import run_sqlite_migrations
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from services.parking_service import ParkingService


def _monthly_pass(db_session, vehicle, customer, start_date, end_date):
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="ENTITLEMENT-01",
        price=500_000,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.commit()
    db_session.refresh(monthly_pass)
    return monthly_pass


def _legacy_entitlement_engine(tmp_path, name):
    target = tmp_path / name
    engine = create_engine(f"sqlite:///{target.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE vehicles (id INTEGER PRIMARY KEY, "
            "license_plate TEXT NOT NULL, vehicle_type_id INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE monthly_passes (id INTEGER PRIMARY KEY, "
            "customer_id INTEGER NOT NULL, vehicle_id INTEGER NOT NULL, "
            "pass_code TEXT, price INTEGER NOT NULL DEFAULT 0, "
            "start_date TEXT NOT NULL, end_date TEXT NOT NULL, "
            "is_active INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE price_configs (id INTEGER PRIMARY KEY, "
            "vehicle_type_id INTEGER NOT NULL, ticket_type TEXT NOT NULL, "
            "price INTEGER NOT NULL, effective_date TEXT NOT NULL, "
            "is_active INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE parking_sessions (id TEXT PRIMARY KEY, "
            "vehicle_id INTEGER NOT NULL, parking_slot_id INTEGER, "
            "monthly_pass_id INTEGER, check_in_time TEXT NOT NULL, "
            "check_out_time TEXT, parking_fee INTEGER, status TEXT NOT NULL, "
            "staff_in_id INTEGER NOT NULL, staff_out_id INTEGER)"
        )
    return engine


def test_monthly_pass_expiring_during_stay_falls_back_to_regular_fee(
    db_session,
    test_user,
    vehicle,
    customer,
    parking_slot,
    price_config,
    business_reference_now,
    monkeypatch,
):
    pass_day = business_reference_now.date()
    monthly_pass = _monthly_pass(
        db_session, vehicle, customer, pass_day, pass_day
    )
    check_in_time = datetime.datetime.combine(
        pass_day, datetime.time(23, 30)
    )
    check_out_time = check_in_time + datetime.timedelta(hours=2)
    parking_slot.is_occupied = True
    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=check_in_time,
        status="active",
        staff_in_id=test_user.id,
    )
    db_session.add(session)
    db_session.commit()
    monkeypatch.setattr(crud_parking_session, "server_now", lambda: check_out_time)

    result = ParkingService(db_session).check_out(vehicle.license_plate, test_user.id)

    assert result["parking_fee"] == 2 * price_config.price


def test_deactivating_pass_after_check_in_does_not_revoke_covered_entitlement(
    db_session,
    vehicle,
    customer,
    business_reference_now,
):
    monthly_pass = _monthly_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=5),
    )
    monthly_pass.is_active = False
    db_session.commit()

    fee = ParkingService(db_session).calculate_fee(
        vehicle_id=vehicle.id,
        vehicle_type_id=vehicle.vehicle_type_id,
        time_in=business_reference_now,
        time_out=business_reference_now + datetime.timedelta(hours=2),
        monthly_pass_id=monthly_pass.id,
    )

    assert fee == 0


def test_calculate_fee_rejects_monthly_pass_from_another_vehicle(
    db_session,
    vehicle,
    vehicle_type,
    customer,
    business_reference_now,
):
    other_vehicle = Vehicle(
        license_plate="51A-ENTITLEMENT",
        vehicle_type_id=vehicle_type.id,
    )
    db_session.add(other_vehicle)
    db_session.commit()
    monthly_pass = _monthly_pass(
        db_session,
        other_vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=5),
    )

    with pytest.raises(HTTPException) as exc_info:
        ParkingService(db_session).calculate_fee(
            vehicle_id=vehicle.id,
            vehicle_type_id=vehicle.vehicle_type_id,
            time_in=business_reference_now,
            time_out=business_reference_now + datetime.timedelta(hours=1),
            monthly_pass_id=monthly_pass.id,
        )

    assert exc_info.value.status_code == 500
    assert "quyền lợi" in exc_info.value.detail.lower()


@pytest.mark.parametrize("invalid_case", ["wrong_vehicle", "outside_period"])
def test_db_rejects_ineligible_monthly_pass_snapshot_on_session_insert(
    db_session,
    test_user,
    vehicle,
    vehicle_type,
    customer,
    parking_slot,
    price_config,
    business_reference_now,
    invalid_case,
):
    pass_vehicle = vehicle
    if invalid_case == "wrong_vehicle":
        pass_vehicle = Vehicle(
            license_plate="51A-WRONG-PASS",
            vehicle_type_id=vehicle_type.id,
        )
        db_session.add(pass_vehicle)
        db_session.commit()
    pass_start = business_reference_now.date()
    if invalid_case == "outside_period":
        pass_start += datetime.timedelta(days=1)
    monthly_pass = _monthly_pass(
        db_session,
        pass_vehicle,
        customer,
        pass_start,
        pass_start + datetime.timedelta(days=5),
    )
    db_session.add(
        ParkingSession(
            vehicle_id=vehicle.id,
            parking_slot_id=parking_slot.id,
            monthly_pass_id=monthly_pass.id,
            check_in_time=business_reference_now,
            status="active",
            staff_in_id=test_user.id,
        )
    )

    with pytest.raises(IntegrityError, match="monthly pass is not eligible"):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("vehicle_id", "other_vehicle"),
        ("parking_slot_id", None),
        ("check_in_time", "later"),
        ("staff_in_id", "other_staff"),
    ],
)
def test_db_keeps_session_identity_immutable_after_insert(
    db_session,
    parking_session,
    vehicle_type,
    column,
    replacement,
):
    if replacement == "other_vehicle":
        other_vehicle = Vehicle(
            license_plate="51A-SESSION-ID",
            vehicle_type_id=vehicle_type.id,
        )
        db_session.add(other_vehicle)
        db_session.commit()
        replacement = other_vehicle.id
    elif replacement == "later":
        replacement = parking_session.check_in_time + datetime.timedelta(minutes=1)
    elif replacement == "other_staff":
        # A non-existing FK is enough: the identity trigger must fire first.
        replacement = 999_999

    with pytest.raises(IntegrityError, match="parking session identity is immutable"):
        db_session.execute(
            text(f"UPDATE parking_sessions SET {column} = :value WHERE id = :id"),
            {"value": replacement, "id": parking_session.id},
        )
        db_session.commit()
    db_session.rollback()


def test_db_keeps_monthly_pass_snapshot_immutable_after_insert(
    db_session,
    test_user,
    vehicle,
    customer,
    parking_slot,
    price_config,
    business_reference_now,
):
    monthly_pass = _monthly_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=5),
    )
    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now,
        status="active",
        staff_in_id=test_user.id,
    )
    db_session.add(session)
    db_session.commit()

    with pytest.raises(IntegrityError, match="parking session identity is immutable"):
        db_session.execute(
            text(
                "UPDATE parking_sessions SET monthly_pass_id=NULL "
                "WHERE id=:id"
            ),
            {"id": session.id},
        )
        db_session.commit()
    db_session.rollback()


def test_db_keeps_completed_billing_and_status_immutable(
    db_session,
    parking_session,
    test_user,
    business_reference_now,
):
    completed_at = business_reference_now + datetime.timedelta(hours=2)
    db_session.execute(
        text(
            "UPDATE parking_sessions SET status='completed', "
            "check_out_time=:time, parking_fee=50000, staff_out_id=:staff "
            "WHERE id=:id"
        ),
        {"time": completed_at, "staff": test_user.id, "id": parking_session.id},
    )
    db_session.commit()

    with pytest.raises(
        IntegrityError, match="completed parking session billing is immutable"
    ):
        db_session.execute(
            text("UPDATE parking_sessions SET parking_fee=1 WHERE id=:id"),
            {"id": parking_session.id},
        )
        db_session.commit()
    db_session.rollback()

    with pytest.raises(
        IntegrityError, match="completed parking session is terminal"
    ):
        db_session.execute(
            text("UPDATE parking_sessions SET status='active' WHERE id=:id"),
            {"id": parking_session.id},
        )
        db_session.commit()
    db_session.rollback()


def test_migration_fails_loudly_for_invalid_legacy_monthly_pass_link(tmp_path):
    engine = _legacy_entitlement_engine(tmp_path, "invalid-pass-link.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO vehicles VALUES (1, '51A-ONE', 1), "
            "(2, '51A-TWO', 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO monthly_passes VALUES "
            "(1, 1, 2, 'LEGACY-PASS', 0, '2026-01-01', "
            "'2026-01-31', 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, monthly_pass_id, check_in_time, status, staff_in_id) "
            "VALUES ('bad-pass-link', 1, 1, '2026-01-15 08:00:00', "
            "'active', 1)"
        )

    with pytest.raises(RuntimeError, match="monthly_pass_id legacy"):
        run_sqlite_migrations(engine)
    engine.dispose()


def test_migration_fails_loudly_for_active_session_without_rate(tmp_path):
    engine = _legacy_entitlement_engine(tmp_path, "missing-active-rate.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO vehicles VALUES (1, '51A-NO-RATE', 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, monthly_pass_id, check_in_time, status, staff_in_id) "
            "VALUES ('missing-rate', 1, NULL, '2026-01-15 08:00:00', "
            "'active', 1)"
        )

    with pytest.raises(RuntimeError, match="thiếu bảng giá dự phòng hiệu lực"):
        run_sqlite_migrations(engine)
    engine.dispose()
