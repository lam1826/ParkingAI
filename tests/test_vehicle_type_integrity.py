"""Regression tests for vehicle-type immutability once business history exists.

The public seam is the vehicle management API: callers must not be able to
rewrite the type used by an active or historical parking transaction.
"""

from datetime import timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from services.auth_service import AuthService


def _headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


def _other_vehicle_type(db: Session) -> VehicleType:
    vehicle_type = VehicleType(name="Xe máy", description="Loại xe khác")
    db.add(vehicle_type)
    db.commit()
    db.refresh(vehicle_type)
    return vehicle_type


def test_cannot_change_vehicle_type_while_vehicle_has_active_session(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_session: ParkingSession,
):
    original_type_id = vehicle.vehicle_type_id
    original_plate = vehicle.license_plate
    other_type = _other_vehicle_type(db_session)
    headers = _headers(test_user)

    response = client.put(
        f"/api/v1/vehicles/{vehicle.id}",
        headers=headers,
        json={
            "license_plate": "30A-CHANGED",
            "vehicle_type_id": other_type.id,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Không thể đổi loại xe vì phương tiện đã có phiên gửi xe "
        "hoặc vé tháng."
    )

    persisted = client.get(f"/api/v1/vehicles/{vehicle.id}", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json()["vehicle_type_id"] == original_type_id
    assert persisted.json()["license_plate"] == original_plate


def test_cannot_change_vehicle_type_after_monthly_pass_history(
    client: TestClient,
    db_session: Session,
    test_user: User,
    customer: Customer,
    vehicle: Vehicle,
    business_reference_now,
):
    vehicle.customer_id = customer.id
    reference_day = business_reference_now.date()
    db_session.add(MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="TYPE-HISTORY-01",
        price=500_000,
        start_date=reference_day - timedelta(days=60),
        end_date=reference_day - timedelta(days=30),
        is_active=False,
    ))
    db_session.commit()

    original_type_id = vehicle.vehicle_type_id
    other_type = _other_vehicle_type(db_session)
    headers = _headers(test_user)

    response = client.put(
        f"/api/v1/vehicles/{vehicle.id}",
        headers=headers,
        json={"vehicle_type_id": other_type.id},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Không thể đổi loại xe vì phương tiện đã có phiên gửi xe "
        "hoặc vé tháng."
    )

    persisted = client.get(f"/api/v1/vehicles/{vehicle.id}", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json()["vehicle_type_id"] == original_type_id


def test_cannot_change_vehicle_type_after_completed_parking_history(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    parking_session: ParkingSession,
):
    # Phiên completed phải có ĐỦ billing theo contract vòng đời ở tầng DB.
    parking_session.status = "completed"
    parking_session.check_out_time = parking_session.check_in_time
    parking_session.parking_fee = 0
    parking_session.staff_out_id = test_user.id
    db_session.commit()
    original_type_id = vehicle.vehicle_type_id
    other_type = _other_vehicle_type(db_session)
    headers = _headers(test_user)

    response = client.put(
        f"/api/v1/vehicles/{vehicle.id}",
        headers=headers,
        json={"vehicle_type_id": other_type.id},
    )

    assert response.status_code == 409
    persisted = client.get(f"/api/v1/vehicles/{vehicle.id}", headers=headers)
    assert persisted.status_code == 200
    assert persisted.json()["vehicle_type_id"] == original_type_id


def test_vehicle_with_active_session_can_update_customer_with_same_identity(
    client: TestClient,
    test_user: User,
    customer: Customer,
    vehicle: Vehicle,
    parking_session: ParkingSession,
):
    headers = _headers(test_user)
    response = client.put(
        f"/api/v1/vehicles/{vehicle.id}",
        headers=headers,
        json={
            "license_plate": vehicle.license_plate,
            # CrudPage gửi lại toàn bộ form khi edit; cùng loại xe không
            # phải là thay đổi nghiệp vụ và không được bị chặn.
            "vehicle_type_id": vehicle.vehicle_type_id,
            "customer_id": customer.id,
        },
    )

    assert response.status_code == 200
    assert response.json()["license_plate"] == vehicle.license_plate
    assert response.json()["vehicle_type_id"] == vehicle.vehicle_type_id
    assert response.json()["customer"]["id"] == customer.id


def test_cannot_change_license_plate_after_parking_history(
    client: TestClient,
    test_user: User,
    vehicle: Vehicle,
    parking_session: ParkingSession,
):
    original_plate = vehicle.license_plate
    response = client.put(
        f"/api/v1/vehicles/{vehicle.id}",
        headers=_headers(test_user),
        json={"license_plate": "51H-456.78"},
    )

    assert response.status_code == 409
    assert "biển số" in response.json()["detail"].lower()
    assert vehicle.license_plate == original_plate


def test_db_trigger_blocks_license_plate_change_after_parking_history(
    db_session: Session,
    vehicle: Vehicle,
    parking_session: ParkingSession,
):
    original_plate = vehicle.license_plate
    with pytest.raises(IntegrityError, match="license plate immutable after history"):
        db_session.execute(
            update(Vehicle)
            .where(Vehicle.id == vehicle.id)
            .values(license_plate="51H-DIRECT")
        )
        db_session.commit()

    db_session.rollback()
    assert db_session.get(Vehicle, vehicle.id).license_plate == original_plate


def test_db_trigger_blocks_vehicle_type_change_after_parking_history(
    db_session: Session,
    vehicle: Vehicle,
    parking_session: ParkingSession,
):
    """Backstop DB phải chặn đường ghi trực tiếp và cửa TOCTOU ngoài router."""
    original_type_id = vehicle.vehicle_type_id
    other_type = _other_vehicle_type(db_session)

    with pytest.raises(IntegrityError, match="vehicle type immutable after history"):
        db_session.execute(
            update(Vehicle)
            .where(Vehicle.id == vehicle.id)
            .values(vehicle_type_id=other_type.id)
        )
        db_session.commit()

    db_session.rollback()
    assert db_session.get(Vehicle, vehicle.id).vehicle_type_id == original_type_id


def test_db_trigger_blocks_vehicle_type_change_after_monthly_pass_history(
    db_session: Session,
    customer: Customer,
    vehicle: Vehicle,
    business_reference_now,
):
    vehicle.customer_id = customer.id
    reference_day = business_reference_now.date()
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="TYPE-DB-BACKSTOP",
        price=500_000,
        start_date=reference_day - timedelta(days=60),
        end_date=reference_day - timedelta(days=30),
        is_active=False,
    )
    db_session.add(monthly_pass)
    db_session.commit()
    original_type_id = vehicle.vehicle_type_id
    other_type = _other_vehicle_type(db_session)

    with pytest.raises(IntegrityError, match="vehicle type immutable after history"):
        db_session.execute(
            update(Vehicle)
            .where(Vehicle.id == vehicle.id)
            .values(vehicle_type_id=other_type.id)
        )
        db_session.commit()

    db_session.rollback()
    assert db_session.get(Vehicle, vehicle.id).vehicle_type_id == original_type_id


def test_db_trigger_allows_vehicle_type_change_before_business_history(
    db_session: Session,
    vehicle: Vehicle,
):
    other_type = _other_vehicle_type(db_session)

    db_session.execute(
        update(Vehicle)
        .where(Vehicle.id == vehicle.id)
        .values(vehicle_type_id=other_type.id)
    )
    db_session.commit()

    assert db_session.get(Vehicle, vehicle.id).vehicle_type_id == other_type.id
