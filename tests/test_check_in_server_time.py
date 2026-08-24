"""Regression test Đợt 5: server-authoritative check_in_time + schema forbid.

- Client không thể gửi check_in_time / parking_fee / status / staff_in_id /
  monthly_pass_id / field lạ vào bất kỳ endpoint check-in nào (422, DB nguyên).
- Đồng hồ server (crud.parking_session.server_now) được gọi ĐÚNG MỘT LẦN mỗi
  check-in thành công; cùng timestamp dùng cho session, ngày tra vé tháng và
  response. Freeze bằng monkeypatch, không đổi đồng hồ hệ thống.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import crud.parking_session as crud_session_module
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from services.auth_service import AuthService

FORBIDDEN_FIELDS = [
    ("check_in_time", "2020-01-01T00:00:00"),
    ("parking_fee", 0),
    ("status", "completed"),
    ("staff_in_id", 999),
    ("monthly_pass_id", 123),
    ("bogus_field", 1),
]


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    token = AuthService().create_access_token(
        user_id=test_user.id, username=test_user.username, role=str(test_user.role)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def frozen_clock(monkeypatch):
    """Freeze server_now tại một thời điểm và đếm số lần được gọi."""

    def freeze(frozen_at: datetime.datetime) -> dict:
        calls = {"n": 0}

        def fake_now() -> datetime.datetime:
            calls["n"] += 1
            return frozen_at

        monkeypatch.setattr(crud_session_module, "server_now", fake_now)
        return calls

    return freeze


# ===========================================================================
# 1. Forbidden fields — endpoint theo ID
# ===========================================================================


@pytest.mark.parametrize("field_name,value", FORBIDDEN_FIELDS)
def test_id_based_check_in_rejects_forbidden_fields(
    field_name, value,
    client: TestClient, auth_headers, db_session: Session,
    vehicle: Vehicle, parking_slot: ParkingSlot,
):
    response = client.post(
        "/api/v1/parking-sessions/check-in",
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id,
              field_name: value},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert field_name in str(response.json()["detail"])

    assert db_session.query(ParkingSession).count() == 0, "Không được tạo session"
    db_session.refresh(parking_slot)
    assert parking_slot.is_occupied is False, "Slot không được claim"


# ===========================================================================
# 2. Forbidden fields — /parking/check-in (422 TRƯỚC mọi side effect)
# ===========================================================================


@pytest.mark.parametrize("field_name,value", FORBIDDEN_FIELDS)
def test_parking_check_in_rejects_forbidden_fields(
    field_name, value,
    client: TestClient, auth_headers, db_session: Session,
    vehicle_type: VehicleType, parking_slot: ParkingSlot,
):
    new_plate = "95Z-55555"  # biển số CHƯA tồn tại

    response = client.post(
        "/parking/check-in",
        json={"license_plate": new_plate, "vehicle_type_id": vehicle_type.id,
              field_name: value},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert field_name in str(response.json()["detail"])

    # 422 phải xảy ra trước khi tạo vehicle, claim slot hoặc tạo session
    created = db_session.query(Vehicle).filter_by(license_plate=new_plate).first()
    assert created is None, "Vehicle không được tạo khi payload bị từ chối"
    assert db_session.query(ParkingSession).count() == 0
    db_session.refresh(parking_slot)
    assert parking_slot.is_occupied is False


# ===========================================================================
# 3+4. Server-authoritative time trên cả hai endpoint (clock gọi đúng 1 lần)
# ===========================================================================


def test_id_based_check_in_uses_server_clock_once(
    client: TestClient, auth_headers, db_session: Session,
    vehicle: Vehicle, parking_slot: ParkingSlot, frozen_clock,
):
    frozen = datetime.datetime(2026, 9, 1, 8, 30, 0)
    calls = frozen_clock(frozen)

    response = client.post(
        "/api/v1/parking-sessions/check-in",
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["check_in_time"] == frozen.isoformat()
    assert calls["n"] == 1, f"Clock phải được gọi đúng 1 lần, thực tế {calls['n']}"

    session = db_session.query(ParkingSession).filter_by(vehicle_id=vehicle.id).one()
    assert session.check_in_time == frozen


def test_parking_check_in_uses_server_clock_once(
    client: TestClient, auth_headers, db_session: Session,
    vehicle: Vehicle, vehicle_type: VehicleType, parking_slot: ParkingSlot,
    frozen_clock,
):
    frozen = datetime.datetime(2026, 9, 1, 9, 15, 0)
    calls = frozen_clock(frozen)

    response = client.post(
        "/parking/check-in",
        json={"license_plate": vehicle.license_plate,
              "vehicle_type_id": vehicle_type.id},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["check_in_time"] == frozen.isoformat()
    assert calls["n"] == 1, f"Clock phải được gọi đúng 1 lần, thực tế {calls['n']}"

    session = db_session.query(ParkingSession).filter_by(vehicle_id=vehicle.id).one()
    assert session.check_in_time == frozen


# ===========================================================================
# 5. Phí tính từ T do server lưu — client không thể tác động
# ===========================================================================


def test_fee_computed_from_server_check_in_time(
    client: TestClient, auth_headers, db_session: Session,
    vehicle: Vehicle, parking_slot: ParkingSlot, price_config, frozen_clock,
):
    check_in_at = datetime.datetime(2026, 9, 2, 10, 0, 0)
    calls = frozen_clock(check_in_at)

    created = client.post(
        "/api/v1/parking-sessions/check-in",
        json={"vehicle_id": vehicle.id, "parking_slot_id": parking_slot.id},
        headers=auth_headers,
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert calls["n"] == 1

    # Checkout đúng 2 giờ sau theo đồng hồ SERVER
    calls_out = frozen_clock(check_in_at + datetime.timedelta(hours=2))
    checked_out = client.put(
        f"/api/v1/parking-sessions/{session_id}/check-out",
        json={},
        headers=auth_headers,
    )

    assert checked_out.status_code == 200
    assert checked_out.json()["parking_fee"] == price_config.price * 2
    assert calls_out["n"] == 1


# ===========================================================================
# 6. Vé tháng tại boundary ngày (sát nửa đêm) — cùng T.date()
# ===========================================================================


def test_monthly_pass_attached_using_frozen_date_at_midnight_boundary(
    client: TestClient, auth_headers, db_session: Session,
    customer, vehicle: Vehicle, vehicle_type: VehicleType,
    parking_slot: ParkingSlot, frozen_clock,
):
    """Vé CHỈ hiệu lực đúng một ngày D trong tương lai; check-in frozen tại
    D 23:59:59 phải gắn được vé — chứng minh ngày tra vé lấy từ chính
    timestamp T (một lần gọi clock), không phải một datetime.now() thứ hai."""
    pass_day = datetime.date.today() + datetime.timedelta(days=30)
    frozen = datetime.datetime.combine(pass_day, datetime.time(23, 59, 59))

    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=pass_day, end_date=pass_day, is_active=True,
    ))
    db_session.commit()

    calls = frozen_clock(frozen)
    response = client.post(
        "/parking/check-in",
        json={"license_plate": vehicle.license_plate,
              "vehicle_type_id": vehicle_type.id},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["monthly_pass_id"] is not None, (
        "Vé hiệu lực đúng ngày T.date() phải được gắn"
    )
    assert calls["n"] == 1

    session = db_session.query(ParkingSession).filter_by(vehicle_id=vehicle.id).one()
    assert session.check_in_time == frozen
    assert session.monthly_pass_id is not None


def test_expired_monthly_pass_not_attached_with_frozen_clock(
    client: TestClient, auth_headers, db_session: Session,
    customer, vehicle: Vehicle, vehicle_type: VehicleType,
    parking_slot: ParkingSlot, frozen_clock,
):
    pass_day = datetime.date.today() + datetime.timedelta(days=30)
    frozen = datetime.datetime.combine(pass_day, datetime.time(0, 0, 1))

    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=pass_day - datetime.timedelta(days=40),
        end_date=pass_day - datetime.timedelta(days=1),  # hết hạn hôm trước
        is_active=True,
    ))
    db_session.commit()

    frozen_clock(frozen)
    response = client.post(
        "/parking/check-in",
        json={"license_plate": vehicle.license_plate,
              "vehicle_type_id": vehicle_type.id},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["monthly_pass_id"] is None, "Vé hết hạn không được gắn"


# ===========================================================================
# 7. Rollback sau claim vẫn đúng với server clock
# ===========================================================================


def test_rollback_after_claim_with_server_clock(
    client: TestClient, auth_headers, db_session: Session,
    vehicle: Vehicle, vehicle_type: VehicleType, parking_slot: ParkingSlot,
    frozen_clock,
):
    frozen_clock(datetime.datetime(2026, 9, 3, 12, 0, 0))
    engine = db_session.get_bind()
    armed = {"on": True}

    @event.listens_for(engine, "before_cursor_execute")
    def break_insert(conn, cursor, statement, params, ctx, many):
        if armed["on"] and statement.lstrip().upper().startswith(
            "INSERT INTO PARKING_SESSIONS"
        ):
            armed["on"] = False
            raise OperationalError("forced", {}, Exception("ép lỗi INSERT"))

    try:
        response = client.post(
            "/parking/check-in",
            json={"license_plate": vehicle.license_plate,
                  "vehicle_type_id": vehicle_type.id},
            headers=auth_headers,
        )
    finally:
        event.remove(engine, "before_cursor_execute", break_insert)

    assert response.status_code == 500
    assert "sqlite3" not in str(response.json())

    db_session.rollback()
    assert db_session.query(ParkingSession).count() == 0, "Không session rác"
    db_session.refresh(parking_slot)
    assert parking_slot.is_occupied is False, "Slot phải được trả về free"


# ===========================================================================
# 8. OpenAPI contract
# ===========================================================================


def test_openapi_request_schemas_hide_server_fields(client: TestClient):
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]

    forbidden = {"check_in_time", "parking_fee", "status", "staff_in_id",
                 "monthly_pass_id"}
    for schema_name in ("CheckInRequest", "ParkingSessionCreate"):
        props = set(schemas[schema_name].get("properties", {}).keys())
        leaked = props & forbidden
        assert not leaked, f"{schema_name} vẫn công bố field server: {leaked}"
        assert schemas[schema_name].get("additionalProperties") is False

    # Response vẫn phải có check_in_time (không đổi contract đọc)
    response_props = schemas["ParkingSessionResponse"]["properties"]
    assert "check_in_time" in response_props


# ===========================================================================
# 10. Dead code đã bị loại bỏ
# ===========================================================================


def test_wide_update_surface_removed():
    import crud.parking_session as crud_ps
    import schemas.parking_session as schemas_ps

    assert not hasattr(schemas_ps, "ParkingSessionUpdate"), (
        "ParkingSessionUpdate phải bị xóa — bề mặt update chứa field tài chính"
    )
    assert not hasattr(crud_ps, "update_parking_session"), (
        "update_parking_session phải bị xóa — không còn caller"
    )
