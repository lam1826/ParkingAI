import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Integer
from sqlalchemy.exc import IntegrityError
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
from core.money import MAX_EXACT_VND


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


# ===========================================================================
# Timezone-independence: ghim MỘT reference instant cho cả file
# ===========================================================================
#
# BUG ĐÃ SỬA (CI đỏ trên GitHub Actions, runner chạy host UTC):
# `test_crud_check_out_server_calculates_fee` đặt `check_in_time` bằng
# `datetime.datetime.now()` — naive theo timezone của HOST. Trong khi đó
# production `server_now()` (crud/parking_session.py) trả naive
# business-local Asia/Ho_Chi_Minh. Hai giá trị naive thuộc HAI hệ quy chiếu
# khác nhau bị trừ trực tiếp khi tính phí:
#
#   duration = server_now() - check_in_time
#            = (UTC_now + 7h) - (UTC_now - 30 phút)
#            = 7 giờ 30 phút          <- thay vì đúng 30 phút
#
# -> làm tròn lên 8 giờ -> phí 200.000 thay vì 25.000 (đúng 1 giờ tối thiểu).
# Trên máy dev Việt Nam (host = UTC+7) hai hệ quy chiếu trùng nhau nên bug
# ẩn hoàn toàn; chỉ lộ ra trên CI.
#
# CÁCH SỬA (không đụng production fee logic):
# - Một reference instant NAIVE BUSINESS-LOCAL cố định cho toàn file.
# - Override fixture `business_reference_now` của conftest.py -> mọi fixture
#   dẫn xuất (`parking_session.check_in_time`, `price_config.effective_date`)
#   đều neo vào đúng mốc này.
# - Ghim luôn seam `crud.parking_session.server_now()` về CÙNG mốc đó, nên
#   cả hai vế của phép trừ chắc chắn cùng hệ quy chiếu.
# Kết quả: mọi test trong file độc lập với timezone host, ngày chạy và thời
# điểm chạy.

CHECKOUT_REFERENCE_NOW = datetime.datetime(2026, 8, 25, 1, 35, 34)


@pytest.fixture()
def business_reference_now() -> datetime.datetime:
    """Override fixture cùng tên trong conftest.py: ghim toàn bộ
    test_check_out.py vào một mốc business-local cố định."""
    return CHECKOUT_REFERENCE_NOW


@pytest.fixture(autouse=True)
def freeze_server_clock(monkeypatch, business_reference_now: datetime.datetime):
    """Ghim đồng hồ server về đúng reference instant.

    Patch tại `crud.parking_session.server_now` — seam chuẩn đã dùng sẵn ở
    `tests/test_check_out_concurrency.py`; cả hai đường check-out
    (`POST /parking/check-out` và `PUT /api/v1/parking-sessions/{id}/check-out`)
    đều đi qua seam này."""
    import crud.parking_session as crud_session_module

    monkeypatch.setattr(
        crud_session_module, "server_now", lambda: business_reference_now
    )


def test_check_out_success(
    client: TestClient,
    auth_headers: dict,
    vehicle: Vehicle,
    parking_session: ParkingSession,
    price_config
):
    """1. Kiểm thử xe ra bãi (check-out) thành công với phiên đang hoạt động."""
    payload = {
        "license_plate": vehicle.license_plate
    }

    response = client.post("/parking/check-out", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["license_plate"] == vehicle.license_plate
    assert data["status"] == "completed"
    assert "parking_fee" in data
    assert type(data["parking_fee"]) is int


def test_check_out_non_existent_vehicle(
    client: TestClient,
    auth_headers: dict
):
    """2. Kiểm thử check-out thất bại khi xe không tồn tại hoặc không có trong bãi."""
    payload = {
        "license_plate": "99Z-999.99"
    }

    response = client.post("/parking/check-out", json=payload, headers=auth_headers)

    assert response.status_code == 404
    detail_msg = response.json().get("detail", "").lower()
    assert "không tìm thấy" in detail_msg


def test_check_out_already_checked_out(
    client: TestClient,
    auth_headers: dict,
    vehicle: Vehicle,
    parking_session: ParkingSession,
    price_config
):
    """3. Kiểm thử check-out thất bại khi xe đã ra rồi (phiên đã kết thúc, không còn phiên active nào để tìm)."""
    payload = {
        "license_plate": vehicle.license_plate
    }

    # Check-out lần 1 (thành công)
    response_1 = client.post("/parking/check-out", json=payload, headers=auth_headers)
    assert response_1.status_code == 200

    # Check-out lần 2 (thất bại vì không còn phiên "active" nào cho biển số này)
    response_2 = client.post("/parking/check-out", json=payload, headers=auth_headers)
    assert response_2.status_code == 404


def test_check_out_monthly_pass(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    customer: Customer,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
    test_user: User,
    # Mọi lượt vào — kể cả xe có vé tháng — đều phải có bảng giá fallback
    # active/effective tại check-in (trg_..._rate_insert_validation_v2). Vé
    # tháng chỉ quyết định phí = 0 khi quyền lợi còn bao phủ ngày xe ra.
    price_config,
    business_reference_now: datetime.datetime,
):
    """4. Kiểm thử check-out đối với xe có vé tháng còn hiệu lực (phí = 0)."""
    plate = "PASS-123.45"

    vehicle = Vehicle(license_plate=plate, vehicle_type_id=vehicle_type.id, customer_id=customer.id)
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    reference_day = business_reference_now.date()
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=reference_day - datetime.timedelta(days=5),
        end_date=reference_day + datetime.timedelta(days=25),
        is_active=True
    )
    db_session.add(monthly_pass)
    db_session.flush()

    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now - datetime.timedelta(hours=2),
        status="active",
        staff_in_id=test_user.id
    )
    parking_slot.is_occupied = True
    db_session.add(session)
    db_session.commit()

    payload = {"license_plate": plate}
    response = client.post("/parking/check-out", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["parking_fee"] == 0
    assert type(data["parking_fee"]) is int


def test_check_out_uses_monthly_pass_entitlement_snapshotted_at_check_in(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    customer: Customer,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    test_user: User,
    # Bảng giá fallback bắt buộc theo chính sách admission; assert bên dưới
    # vẫn phải là 0 vì entitlement snapshot lúc check-in còn bao phủ.
    price_config,
    business_reference_now: datetime.datetime,
):
    """Hủy vé sau check-in không được viết lại quyền lợi của phiên đã gắn vé."""
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="SNAPSHOT-ENTITLEMENT",
        price=500_000,
        start_date=business_reference_now.date() - datetime.timedelta(days=1),
        end_date=business_reference_now.date() + datetime.timedelta(days=1),
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.flush()
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now - datetime.timedelta(minutes=1),
        status="active",
        staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(parking_session)
    db_session.commit()
    monthly_pass.is_active = False
    db_session.commit()

    response = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["parking_fee"] == 0


def test_pass_bought_after_check_in_does_not_retroactively_make_stay_free(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    customer: Customer,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    test_user: User,
    price_config,
    business_reference_now: datetime.datetime,
):
    """Entitlement is the session FK, not whichever active pass exists later."""
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=business_reference_now - datetime.timedelta(minutes=1),
        status="active",
        staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(parking_session)
    db_session.commit()
    assert parking_session.monthly_pass_id is None
    db_session.add(MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="BOUGHT-AFTER-ENTRY",
        price=500_000,
        start_date=business_reference_now.date() - datetime.timedelta(days=1),
        end_date=business_reference_now.date() + datetime.timedelta(days=1),
        is_active=True,
    ))
    db_session.commit()

    response = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["parking_fee"] == price_config.price


@pytest.mark.parametrize("invalid_fee", [1000.5, -1])
def test_db_trigger_rejects_invalid_parking_fee_direct_write(
    db_session: Session,
    parking_session: ParkingSession,
    invalid_fee,
):
    session_id = parking_session.id
    assert parking_session.parking_fee is None

    parking_session.parking_fee = invalid_fee
    with pytest.raises(
        IntegrityError,
        match="parking fee must be nonnegative integer",
    ):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(ParkingSession, session_id).parking_fee is None


def test_db_trigger_rejects_parking_fee_above_exact_vnd_range(
    db_session: Session,
    parking_session: ParkingSession,
):
    parking_session.parking_fee = MAX_EXACT_VND + 1
    with pytest.raises(
        IntegrityError,
        match="parking fee exceeds exact VND range",
    ):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(ParkingSession, parking_session.id).parking_fee is None


def test_parking_fee_contract_is_integer_in_model_and_openapi(
    client: TestClient,
):
    assert isinstance(ParkingSession.__table__.c.parking_fee.type, Integer)

    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert schemas["CheckOutResponse"]["properties"]["parking_fee"]["type"] == "integer"
    assert (
        schemas["ParkingSessionDetailResponse"]["properties"]["parking_fee"]["type"]
        == "integer"
    )
    nullable_fee = schemas["ParkingSessionResponse"]["properties"]["parking_fee"]
    assert {item.get("type") for item in nullable_fee["anyOf"]} == {
        "integer",
        "null",
    }


def test_check_out_fee_calculation(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot,
    price_config,
    test_user: User,
    business_reference_now: datetime.datetime,
):
    """5. Kiểm thử tính phí gửi xe theo giờ dựa trên PriceConfig.price."""
    plate = "FEE-456.78"
    vehicle = Vehicle(license_plate=plate, vehicle_type_id=vehicle_type.id)
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    # Đúng 3 giờ tính từ reference instant -> phí phải bằng CHÍNH XÁC 3 x đơn giá
    check_in_time = business_reference_now - datetime.timedelta(hours=3)

    session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=check_in_time,
        status="active",
        staff_in_id=test_user.id
    )
    parking_slot.is_occupied = True
    db_session.add(session)
    db_session.commit()

    payload = {"license_plate": plate}
    response = client.post("/parking/check-out", json=payload, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    fee = data["parking_fee"]

    # Phiên đúng 3 giờ chẵn -> phí xác định, không phụ thuộc thời điểm chạy test
    assert fee == price_config.price * 3, (
        f"Phiên gửi đúng 3 giờ phải có phí = {price_config.price * 3}, thực tế={fee}"
    )


def test_check_out_slot_becomes_available(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle: Vehicle,
    parking_session: ParkingSession,
    parking_slot: ParkingSlot,
    price_config
):
    """6. Kiểm thử vị trí đỗ xe (ParkingSlot) tự động chuyển is_occupied=False sau khi xe check-out thành công."""
    payload = {
        "license_plate": vehicle.license_plate
    }

    response = client.post("/parking/check-out", json=payload, headers=auth_headers)

    assert response.status_code == 200

    db_session.refresh(parking_slot)
    assert parking_slot.is_occupied is False


def test_crud_check_out_server_calculates_fee(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle: Vehicle,
    parking_slot: ParkingSlot,
    test_user: User,
    price_config,
    business_reference_now: datetime.datetime,
):
    """7. Kiểm thử đường check-out phụ /api/v1/parking-sessions/{id}/check-out:
    phí do SERVER tính từ bảng giá; body rỗng; vị trí được giải phóng."""
    # Giờ vào = 30 phút trước reference instant. Trước đây dùng
    # `datetime.datetime.now()` (naive theo host) nên lệch 7 giờ so với
    # `server_now()` business-local khi CI chạy trên host UTC.
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=business_reference_now - datetime.timedelta(minutes=30),
        status="active",
        staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(parking_session)
    db_session.commit()

    response = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    # Phiên gửi vừa check-in xong (< 1 giờ) -> làm tròn lên 1 giờ theo bảng giá
    assert data["parking_fee"] == price_config.price

    db_session.refresh(parking_slot)
    assert parking_slot.is_occupied is False


def test_crud_check_out_is_idempotent(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    parking_session: ParkingSession,
    price_config,
):
    """8. PUT check-out là IDEMPOTENT: các lần gọi lại trả 200 với đúng dữ liệu
    đã persist — không tính lại phí, không đổi thời gian/nhân viên."""
    first = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )
    assert first.status_code == 200
    first_data = first.json()

    second = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )
    assert second.status_code == 200
    second_data = second.json()

    assert second_data["parking_fee"] == first_data["parking_fee"]
    assert second_data["check_out_time"] == first_data["check_out_time"]
    assert second_data["status"] == "completed"
