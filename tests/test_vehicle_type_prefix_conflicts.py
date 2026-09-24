"""Duplicate identification prefixes must not be reported as duplicate names."""
import pytest
from sqlalchemy import func, select

from models.vehicle_type import VehicleType
from services.auth_service import AuthService


@pytest.mark.parametrize("operation", ["create", "update"])
def test_duplicate_prefix_has_correct_message_and_keeps_records_unchanged(
    operation, client, db_session, manager_user,
):
    first = VehicleType(name="Xe đạp thường", requires_plate=False, code_prefix="CYCLE")
    second = VehicleType(name="Xe đạp điện", requires_plate=False, code_prefix="ELEC")
    db_session.add_all([first, second])
    db_session.commit()
    second_id = second.id
    initial_count = db_session.scalar(select(func.count(VehicleType.id)))
    token = AuthService().create_access_token(
        user_id=manager_user.id, username=manager_user.username, role=manager_user.role.name,
    )
    payload = {"name": "Tên loại xe hoàn toàn mới", "requires_plate": False, "code_prefix": "CYCLE"}
    request = client.post if operation == "create" else client.put
    path = "/api/v1/vehicle-types" + ("" if operation == "create" else f"/{second_id}")
    response = request(path, json=payload, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Tiền tố mã loại xe đã tồn tại. Hãy chọn mã khác."
    assert db_session.scalar(select(func.count(VehicleType.id))) == initial_count
    db_session.expire_all()
    unchanged = db_session.get(VehicleType, second_id)
    assert (unchanged.name, unchanged.code_prefix) == ("Xe đạp điện", "ELEC")
