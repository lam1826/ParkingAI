"""Regression coverage for the minimal check-in rate provenance contract.

The public seams are the two check-in APIs and the price-config mutation API.
Every stay must have one effective active fallback rate at entry; while that
stay is open, the rate that checkout may use cannot be rewritten or removed.
"""

import datetime
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import crud.parking_session as parking_session_crud
from database import (
    PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL,
    run_sqlite_migrations,
)
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.price_config import PriceConfig
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.zone import Zone
from services.auth_service import AuthService


def _headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=str(user.role),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def frozen_clock(monkeypatch):
    def freeze(frozen_at: datetime.datetime) -> dict[str, int]:
        calls = {"count": 0}

        def fake_now() -> datetime.datetime:
            calls["count"] += 1
            return frozen_at

        monkeypatch.setattr(parking_session_crud, "server_now", fake_now)
        return calls

    return freeze


def _assert_rejected_check_in_is_atomic(
    db: Session,
    slot: ParkingSlot,
    vehicle: Vehicle,
) -> None:
    assert db.query(ParkingSession).filter_by(vehicle_id=vehicle.id).count() == 0
    db.refresh(slot)
    assert slot.is_occupied is False


def test_legacy_check_in_without_effective_price_is_rejected_atomically(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
    frozen_clock,
):
    calls = frozen_clock(datetime.datetime(2026, 9, 8, 8, 0, 0))

    response = client.post(
        "/parking/check-in",
        json={
            "license_plate": vehicle.license_plate,
            "vehicle_type_id": vehicle_type.id,
            "parking_slot_id": parking_slot.id,
        },
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "bảng giá" in response.json()["detail"].lower()
    assert calls["count"] == 1
    _assert_rejected_check_in_is_atomic(db_session, parking_slot, vehicle)


def test_id_check_in_without_effective_price_is_rejected_atomically(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    frozen_clock,
):
    calls = frozen_clock(datetime.datetime(2026, 9, 8, 8, 0, 0))

    response = client.post(
        "/api/v1/parking-sessions/check-in",
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id},
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "bảng giá" in response.json()["detail"].lower()
    assert calls["count"] == 1
    _assert_rejected_check_in_is_atomic(db_session, parking_slot, vehicle)


def test_db_rejects_active_session_without_effective_price(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    business_reference_now: datetime.datetime,
):
    db_session.add(
        ParkingSession(
            vehicle_id=vehicle.id,
            parking_slot_id=parking_slot.id,
            check_in_time=business_reference_now,
            status="active",
            staff_in_id=test_user.id,
        )
    )

    with pytest.raises(
        IntegrityError,
        match="active parking session requires effective price config",
    ):
        db_session.commit()
    db_session.rollback()


def test_db_rejects_monthly_pass_session_without_fallback_price(
    db_session: Session,
    test_user: User,
    customer: Customer,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    business_reference_now: datetime.datetime,
):
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="DIRECT-MONTHLY-NEEDS-RATE",
        price=500_000,
        start_date=business_reference_now.date(),
        end_date=business_reference_now.date() + datetime.timedelta(days=30),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.flush()
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

    with pytest.raises(
        IntegrityError,
        match="active parking session requires effective price config",
    ):
        db_session.commit()
    db_session.rollback()


def test_future_active_price_is_not_effective_for_check_in(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    frozen_clock,
):
    frozen = datetime.datetime(2026, 9, 8, 8, 0, 0)
    db_session.add(
        PriceConfig(
            vehicle_type_id=vehicle.vehicle_type_id,
            ticket_type="HOURLY",
            price=25_000,
            effective_date=frozen.date() + datetime.timedelta(days=1),
            is_active=True,
        )
    )
    db_session.commit()
    calls = frozen_clock(frozen)

    response = client.post(
        "/api/v1/parking-sessions/check-in",
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id},
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert calls["count"] == 1
    _assert_rejected_check_in_is_atomic(db_session, parking_slot, vehicle)


@pytest.mark.parametrize(
    "endpoint",
    ["/parking/check-in", "/api/v1/parking-sessions/check-in"],
)
def test_monthly_pass_check_in_requires_fallback_price(
    endpoint: str,
    client: TestClient,
    db_session: Session,
    test_user: User,
    customer: Customer,
    vehicle: Vehicle,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
    frozen_clock,
):
    frozen = datetime.datetime(2026, 9, 8, 8, 0, 0)
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="RATE-PROVENANCE-PASS",
        price=500_000,
        start_date=frozen.date(),
        end_date=frozen.date() + datetime.timedelta(days=30),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.commit()
    calls = frozen_clock(frozen)

    if endpoint == "/parking/check-in":
        payload = {
            "license_plate": vehicle.license_plate,
            "vehicle_type_id": vehicle_type.id,
            "parking_slot_id": parking_slot.id,
        }
    else:
        payload = {"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id}

    response = client.post(endpoint, json=payload, headers=_headers(test_user))

    assert response.status_code == 409
    assert "bảng giá" in response.json()["detail"].lower()
    assert calls["count"] == 1
    _assert_rejected_check_in_is_atomic(db_session, parking_slot, vehicle)
    assert db_session.query(PriceConfig).count() == 0


@pytest.mark.parametrize(
    "endpoint",
    ["/parking/check-in", "/api/v1/parking-sessions/check-in"],
)
def test_monthly_pass_check_in_snapshots_pass_with_fallback_price(
    endpoint: str,
    client: TestClient,
    db_session: Session,
    test_user: User,
    customer: Customer,
    vehicle: Vehicle,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
    frozen_clock,
):
    frozen = datetime.datetime.combine(
        price_config.effective_date + datetime.timedelta(days=1),
        datetime.time(8, 0),
    )
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="RATE-PROVENANCE-WITH-FALLBACK",
        price=500_000,
        start_date=frozen.date(),
        end_date=frozen.date() + datetime.timedelta(days=30),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.commit()
    calls = frozen_clock(frozen)

    payload = {"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id}
    if endpoint == "/parking/check-in":
        payload = {
            "license_plate": vehicle.license_plate,
            "vehicle_type_id": vehicle_type.id,
            "parking_slot_id": parking_slot.id,
        }

    response = client.post(endpoint, json=payload, headers=_headers(test_user))

    assert response.status_code == 201
    assert calls["count"] == 1
    session = db_session.query(ParkingSession).filter_by(vehicle_id=vehicle.id).one()
    assert session.monthly_pass_id == monthly_pass.id


def test_price_edit_between_entry_and_exit_is_blocked_and_original_fee_persists(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
    frozen_clock,
):
    attempted_price = price_config.price + 99_000

    blocked = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"price": attempted_price},
        headers=_headers(test_user),
    )

    assert blocked.status_code == 409
    assert "phiên gửi xe" in blocked.json()["detail"].lower()
    db_session.refresh(price_config)
    assert price_config.price == 25_000

    frozen_clock(business_reference_now + datetime.timedelta(hours=2))
    checked_out = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=_headers(test_user),
    )

    assert checked_out.status_code == 200
    assert checked_out.json()["parking_fee"] == 50_000
    db_session.refresh(parking_session)
    assert parking_session.parking_fee == 50_000


@pytest.mark.parametrize(
    "payload",
    [
        {"ticket_type": "DAILY"},
        {"effective_date": "2026-09-09"},
        {"is_active": False},
    ],
    ids=["ticket-type", "effective-date", "deactivate"],
)
def test_active_session_blocks_rate_contract_mutation(
    payload: dict,
    client: TestClient,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json=payload,
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "phiên gửi xe" in response.json()["detail"].lower()


def test_active_session_blocks_rate_vehicle_type_change(
    client: TestClient,
    db_session: Session,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    other_type = VehicleType(name="Xe tải khóa giá", description="Loại xe khác")
    db_session.add(other_type)
    db_session.commit()

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"vehicle_type_id": other_type.id},
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "phiên gửi xe" in response.json()["detail"].lower()


def test_active_session_blocks_active_rate_delete(
    client: TestClient,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    response = client.delete(
        f"/api/v1/price-configs/{price_config.id}",
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "phiên gửi xe" in response.json()["detail"].lower()


def test_no_op_update_remains_allowed_while_session_is_active(
    client: TestClient,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"price": price_config.price, "is_active": True},
        headers=_headers(test_user),
    )

    assert response.status_code == 200


def test_db_rejects_rate_rewrite_while_session_is_active(
    db_session: Session,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    with pytest.raises(
        IntegrityError, match="active parking session uses price config"
    ):
        db_session.execute(
            text("UPDATE price_configs SET price=:price WHERE id=:id"),
            {"price": price_config.price + 1, "id": price_config.id},
        )
        db_session.commit()
    db_session.rollback()
    assert db_session.get(PriceConfig, price_config.id).price == price_config.price


def test_db_rejects_active_rate_delete_while_session_is_active(
    db_session: Session,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    config_id = price_config.id
    with pytest.raises(
        IntegrityError, match="active parking session uses price config"
    ):
        db_session.execute(
            text("DELETE FROM price_configs WHERE id=:id"),
            {"id": config_id},
        )
        db_session.commit()
    db_session.rollback()
    assert db_session.get(PriceConfig, config_id) is not None


def test_db_rejects_insert_or_replace_rate_bypass_while_session_is_active(
    db_session: Session,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    assert db_session.execute(text("PRAGMA recursive_triggers")).scalar_one() == 1

    with pytest.raises(
        IntegrityError, match="active parking session uses price config"
    ):
        db_session.execute(
            text(
                "INSERT OR REPLACE INTO price_configs "
                "(id, vehicle_type_id, ticket_type, price, effective_date, "
                "is_active) VALUES (:replacement_id, :vehicle_type_id, "
                "'HOURLY', :price, :effective_date, 1)"
            ),
            {
                "replacement_id": price_config.id + 10_000,
                "vehicle_type_id": price_config.vehicle_type_id,
                "price": price_config.price + 1,
                "effective_date": price_config.effective_date,
            },
        )
        db_session.commit()
    db_session.rollback()

    persisted = db_session.get(PriceConfig, price_config.id)
    assert persisted is not None
    assert persisted.price == price_config.price


def test_monthly_pass_session_locks_fallback_price(
    client: TestClient,
    db_session: Session,
    test_user: User,
    customer: Customer,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="MONTHLY-DOES-NOT-LOCK-RATE",
        price=500_000,
        start_date=business_reference_now.date(),
        end_date=business_reference_now.date() + datetime.timedelta(days=30),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.flush()
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
    parking_slot.is_occupied = True
    db_session.commit()

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"price": 26_000},
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    db_session.refresh(price_config)
    assert price_config.price == 25_000


def test_db_rejects_status_activation_without_effective_price(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    business_reference_now: datetime.datetime,
):
    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=business_reference_now,
        status="cancelled",
        staff_in_id=test_user.id,
    )
    db_session.add(session)
    db_session.commit()

    with pytest.raises(
        IntegrityError,
        match="active parking session requires effective price config",
    ):
        db_session.execute(
            text("UPDATE parking_sessions SET status='active' WHERE id=:id"),
            {"id": session.id},
        )
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("transition", ["insert", "activate"])
def test_db_rejects_active_session_with_slot_vehicle_type_mismatch(
    transition: str,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    other_type = VehicleType(
        name=f"Loại vị trí không khớp {transition}",
        description="DB trigger regression",
    )
    db_session.add(other_type)
    db_session.flush()
    parking_slot.vehicle_type_id = other_type.id
    db_session.commit()

    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=business_reference_now,
        status="cancelled" if transition == "activate" else "active",
        staff_in_id=test_user.id,
    )
    db_session.add(session)

    if transition == "activate":
        db_session.commit()
        statement = text(
            "UPDATE parking_sessions SET status='active' WHERE id=:id"
        )
    with pytest.raises(
        IntegrityError,
        match="parking slot is not eligible for active session",
    ):
        if transition == "activate":
            db_session.execute(statement, {"id": session.id})
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("inactive_target", ["slot", "zone"])
@pytest.mark.parametrize("transition", ["insert", "activate"])
def test_db_rejects_active_session_on_inactive_slot_or_zone(
    inactive_target: str,
    transition: str,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    zone: Zone,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    if inactive_target == "slot":
        parking_slot.is_active = False
    else:
        zone.is_active = False
    db_session.commit()

    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=business_reference_now,
        status="cancelled" if transition == "activate" else "active",
        staff_in_id=test_user.id,
    )
    db_session.add(session)
    if transition == "activate":
        db_session.commit()

    with pytest.raises(
        IntegrityError,
        match="parking slot is not eligible for active session",
    ):
        if transition == "activate":
            db_session.execute(
                text(
                    "UPDATE parking_sessions SET status='active' WHERE id=:id"
                ),
                {"id": session.id},
            )
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("database_message", "expected_fragment"),
    [
        (
            "active parking session requires effective price config",
            "bảng giá",
        ),
        ("monthly pass is not eligible at check-in", "vé tháng"),
        ("parking slot is not eligible for active session", "không phù hợp"),
    ],
)
def test_check_in_integrity_races_map_to_friendly_conflict_messages(
    database_message: str,
    expected_fragment: str,
):
    error = IntegrityError(
        "INSERT INTO parking_sessions ...",
        {},
        sqlite3.IntegrityError(database_message),
    )

    mapped = parking_session_crud.map_check_in_integrity_error(error)

    assert mapped is not None
    assert expected_fragment in mapped.lower()


@pytest.mark.parametrize("operation", ["insert", "update"])
def test_db_rejects_noncanonical_price_effective_date(
    operation: str,
    db_session: Session,
    price_config: PriceConfig,
):
    with pytest.raises(IntegrityError, match="price effective date invalid"):
        if operation == "insert":
            db_session.execute(
                text(
                    "INSERT INTO price_configs "
                    "(vehicle_type_id, ticket_type, price, effective_date, "
                    "is_active) VALUES (:vehicle_type_id, 'HOURLY', 1, "
                    "'not-a-date', 0)"
                ),
                {"vehicle_type_id": price_config.vehicle_type_id},
            )
        else:
            db_session.execute(
                text(
                    "UPDATE price_configs SET effective_date='2026-02-30' "
                    "WHERE id=:id"
                ),
                {"id": price_config.id},
            )
        db_session.commit()
    db_session.rollback()


def test_migration_rejects_legacy_noncanonical_price_effective_date(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'bad-price-date.db').as_posix()}"
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE price_configs (id INTEGER PRIMARY KEY, "
            "vehicle_type_id INTEGER NOT NULL, ticket_type TEXT NOT NULL, "
            "price INTEGER NOT NULL, effective_date TEXT NOT NULL, "
            "is_active INTEGER NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO price_configs VALUES "
            "(1, 1, 'HOURLY', 25000, 'not-a-date', 0)"
        )

    try:
        with pytest.raises(RuntimeError, match="effective_date"):
            run_sqlite_migrations(engine)
    finally:
        engine.dispose()


def test_readiness_rejects_noncanonical_inactive_price_effective_date(tmp_path):
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "readiness-bad-price-date.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA recursive_triggers=ON")
        connection.execute("DROP TRIGGER trg_price_configs_effective_date_insert")
        connection.execute(
            "INSERT INTO price_configs "
            "(vehicle_type_id, ticket_type, price, effective_date, is_active) "
            "VALUES (1, 'HOURLY', 25000, 'not-a-date', 0)"
        )
        connection.execute(PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL)
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="effective_date"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()
