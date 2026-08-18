import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.user import User
from models.zone import Zone
from models.parking_slot import ParkingSlot
from models.vehicle_type import VehicleType
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


def _all_available_slot_ids(payload: dict) -> list:
    ids = []
    for z in payload["zones"]:
        ids.extend(item["id"] for item in z["available_slots_list"])
    return ids


def test_get_available_slots_success(
    client: TestClient,
    auth_headers: dict,
    parking_slot: ParkingSlot
):
    """1. Kiểm thử lấy thông tin chỗ trống thành công khi hệ thống có sẵn slot available."""
    response = client.get("/parking/available-slots", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_available"] >= 1

    # Slot vừa tạo phải xuất hiện trong danh sách trống của khu vực tương ứng
    assert parking_slot.id in _all_available_slot_ids(data)


def test_get_available_slots_parking_full(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    parking_slot: ParkingSlot
):
    """2. Kiểm thử khi bãi đỗ đã hết chỗ (tất cả slot đều is_occupied=True)."""
    slots = db_session.query(ParkingSlot).all()
    for s in slots:
        s.is_occupied = True
    db_session.commit()

    response = client.get("/parking/available-slots", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_available"] == 0
    assert _all_available_slot_ids(data) == []


def test_get_available_slots_grouped_by_zone(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle_type: VehicleType
):
    """3. Kiểm thử danh sách chỗ trống được nhóm đúng theo từng khu vực (Zone)."""
    zone_1 = Zone(name="Khu 1", capacity=10)
    zone_2 = Zone(name="Khu 2", capacity=10)
    db_session.add_all([zone_1, zone_2])
    db_session.commit()
    db_session.refresh(zone_1)
    db_session.refresh(zone_2)

    slot_zone_1 = ParkingSlot(zone_id=zone_1.id, vehicle_type_id=vehicle_type.id, slot_name="Z1-01", is_occupied=False)
    slot_zone_2 = ParkingSlot(zone_id=zone_2.id, vehicle_type_id=vehicle_type.id, slot_name="Z2-01", is_occupied=False)
    db_session.add_all([slot_zone_1, slot_zone_2])
    db_session.commit()
    db_session.refresh(slot_zone_1)
    db_session.refresh(slot_zone_2)

    response = client.get("/parking/available-slots", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    zones_by_id = {z["zone_id"]: z for z in data["zones"]}
    assert zone_1.id in zones_by_id
    assert zone_2.id in zones_by_id

    ids_in_zone_1 = [item["id"] for item in zones_by_id[zone_1.id]["available_slots_list"]]
    ids_in_zone_2 = [item["id"] for item in zones_by_id[zone_2.id]["available_slots_list"]]

    assert slot_zone_1.id in ids_in_zone_1
    assert slot_zone_1.id not in ids_in_zone_2
    assert slot_zone_2.id in ids_in_zone_2
    assert slot_zone_2.id not in ids_in_zone_1


def test_get_available_slots_by_vehicle_type(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle_type: VehicleType,
    parking_slot: ParkingSlot
):
    """4. Kiểm thử slot trống được gắn đúng vehicle_type_id trong danh sách trả về."""
    response = client.get("/parking/available-slots", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    matching = [
        item
        for z in data["zones"]
        for item in z["available_slots_list"]
        if item["id"] == parking_slot.id
    ]
    assert len(matching) == 1
    assert matching[0]["vehicle_type_id"] == vehicle_type.id


def test_get_available_slots_excludes_occupied(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    zone: Zone,
    vehicle_type: VehicleType
):
    """5. Kiểm thử xác nhận danh sách available-slots KHÔNG chứa các slot đã bị chiếm (is_occupied=True)."""
    available_slot = ParkingSlot(zone_id=zone.id, vehicle_type_id=vehicle_type.id, slot_name="AV-01", is_occupied=False)
    occupied_slot = ParkingSlot(zone_id=zone.id, vehicle_type_id=vehicle_type.id, slot_name="OC-01", is_occupied=True)
    db_session.add_all([available_slot, occupied_slot])
    db_session.commit()
    db_session.refresh(available_slot)
    db_session.refresh(occupied_slot)

    response = client.get("/parking/available-slots", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()

    ids = _all_available_slot_ids(data)
    assert available_slot.id in ids
    assert occupied_slot.id not in ids
