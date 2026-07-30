import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.user import User
from models.vehicle_type import VehicleType
from models.zone import Zone
from models.parking_slot import ParkingSlot
from models.customer import Customer
from models.vehicle import Vehicle
from models.parking_session import ParkingSession
from models.monthly_pass import MonthlyPass
from services.auth_service import AuthService


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Fixture tạo Authentication Header (Bearer Token) cho test user."""
    auth_service = AuthService()
    token = auth_service.create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=str(test_user.role)
    )
    return {"Authorization": f"Bearer {token}"}


def test_check_in_success(
    client: TestClient,
    auth_headers: dict,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """1. Kiểm thử xe vào bãi thành công với thông tin hợp lệ (chỗ đỗ được hệ thống tự cấp phát)."""
    payload = {
        "license_plate": "29A-123.45",
        "vehicle_type_id": vehicle_type.id
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["license_plate"] == "29A-123.45"
    assert data["status"] == "active"
    assert "session_id" in data
    assert data["slot_id"] == parking_slot.id


def test_check_in_new_vehicle(
    client: TestClient,
    auth_headers: dict,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """2. Kiểm thử xe mới hoàn toàn đăng ký vào bãi thành công."""
    payload = {
        "license_plate": "51F-888.88",
        "vehicle_type_id": vehicle_type.id
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 201
    assert response.json()["license_plate"] == "51F-888.88"


def test_check_in_vehicle_already_exists(
    client: TestClient,
    auth_headers: dict,
    parking_session: ParkingSession,
    vehicle: Vehicle,
    vehicle_type: VehicleType
):
    """3. Kiểm thử từ chối check-in khi biển số xe đã tồn tại phiên gửi xe đang hoạt động (active)."""
    payload = {
        "license_plate": vehicle.license_plate,  # Biển số đang active sẵn (từ fixture parking_session)
        "vehicle_type_id": vehicle_type.id
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert "đang ở trong bãi" in response.json()["detail"].lower()


def test_check_in_parking_lot_full(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """4. Kiểm thử từ chối check-in khi không còn slot trống phù hợp loại xe (không tìm thấy chỗ -> 404)."""
    slots = db_session.query(ParkingSlot).all()
    for s in slots:
        s.is_occupied = True
    db_session.commit()

    payload = {
        "license_plate": "30H-111.11",
        "vehicle_type_id": vehicle_type.id
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 404
    assert "chỗ trống" in response.json()["detail"].lower()


def test_check_in_missing_license_plate(
    client: TestClient,
    auth_headers: dict,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """5. Kiểm thử lỗi validate khi thiếu trường biển số xe (license_plate)."""
    payload = {
        "vehicle_type_id": vehicle_type.id
        # Thiếu license_plate
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 422  # Pydantic Validation Error


def test_check_in_invalid_vehicle_type(
    client: TestClient,
    auth_headers: dict,
    parking_slot: ParkingSlot
):
    """6. Kiểm thử lỗi khi truyền sai hoặc không tồn tại loại xe (vehicle_type_id)."""
    payload = {
        "license_plate": "15B-333.33",
        "vehicle_type_id": 99999   # Không tồn tại trong DB
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert "loại xe" in response.json()["detail"].lower()


def test_check_in_with_active_monthly_pass(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    customer: Customer,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """7. Kiểm thử xe có vé tháng còn hiệu lực vẫn check-in bình thường
    (vé tháng chỉ ảnh hưởng tới phí lúc check-out, không chặn/gate ở bước check-in)."""
    plate = "99A-555.55"
    vehicle = Vehicle(license_plate=plate, vehicle_type_id=vehicle_type.id, customer_id=customer.id)
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    pass_record = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=datetime.date.today() - datetime.timedelta(days=10),
        end_date=datetime.date.today() + datetime.timedelta(days=20),
        is_active=True
    )
    db_session.add(pass_record)
    db_session.commit()

    payload = {
        "license_plate": plate,
        "vehicle_type_id": vehicle_type.id
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["license_plate"] == plate


def test_check_in_with_expired_monthly_pass(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    customer: Customer,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """8. Kiểm thử xe có vé tháng đã hết hạn vẫn check-in bình thường
    (việc hết hạn chỉ ảnh hưởng tới tính phí ở bước check-out)."""
    plate = "88B-666.66"
    vehicle = Vehicle(license_plate=plate, vehicle_type_id=vehicle_type.id, customer_id=customer.id)
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    pass_record = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=datetime.date.today() - datetime.timedelta(days=40),
        end_date=datetime.date.today() - datetime.timedelta(days=10),
        is_active=False
    )
    db_session.add(pass_record)
    db_session.commit()

    payload = {
        "license_plate": plate,
        "vehicle_type_id": vehicle_type.id
    }

    response = client.post("/parking/check-in", json=payload, headers=auth_headers)

    assert response.status_code == 201
