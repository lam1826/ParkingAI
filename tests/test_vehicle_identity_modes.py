"""Manager/Admin type settings and backwards-compatible server admission identity."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from test_core_crud_permissions import core_access  # noqa: F401


@pytest.mark.parametrize('role', ['manager', 'admin'])
def test_manager_and_admin_define_unplated_type(client, core_access, role):
    response = client.post('/api/v1/vehicle-types', headers=core_access['headers'][role], json={
        'name': 'Xe đạp tự cấp mã', 'requires_plate': False, 'code_prefix': 'XD'})
    assert response.status_code == 201, response.text
    assert response.json()['requires_plate'] is False and response.json()['code_prefix'] == 'XD'
    assert client.post('/api/v1/vehicle-types', headers=core_access['headers'][role], json={
        'name': 'Loại khác cùng mã', 'requires_plate': False, 'code_prefix': 'XD'}).status_code == 409


def test_legacy_type_defaults_plated_and_cannot_change_used_identity_mode(client, core_access):
    headers = core_access['headers']['manager']
    url = f"/api/v1/vehicle-types/{core_access['vehicle-types'].id}"
    assert client.get(url, headers=headers).json()['requires_plate'] is True
    assert client.put(url, headers=headers, json={'requires_plate': False}).status_code == 409
    assert client.put(url, headers=core_access['headers']['staff'], json={'code_prefix': 'STAFF'}).status_code == 403


@pytest.mark.parametrize('body', [
    {'requires_plate': None}, {'requires_plate': 0}, {'requires_plate': 'false'},
    {'code_prefix': ''}, {'code_prefix': 'lower'}, {'code_prefix': '1ABC'}, {'code_prefix': 'ABCDEFGHI'},
])
def test_invalid_identity_settings_rejected(client, core_access, body):
    response = client.post('/api/v1/vehicle-types', headers=core_access['headers']['manager'], json={'name': 'Invalid mode', **body})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('path', ['legacy', 'scoped'])
def test_plated_vehicle_needs_identifier_before_any_admission_write(client, db_session, core_access, path):
    endpoint = '/parking/check-in' if path == 'legacy' else f"/api/v2/sites/{core_access['site'].id}/check-in"
    count = db_session.query(Vehicle).count()
    response = client.post(endpoint, headers=core_access['headers']['staff'], json={
        'vehicle_type_id': core_access['vehicle-types'].id, 'license_plate': ''})
    assert response.status_code == 422, response.text
    assert db_session.query(Vehicle).count() == count
    assert db_session.query(ParkingSession).count() == 0


def test_database_backstop_prevents_mode_change_and_bad_prefix(db_session, core_access):
    identity = core_access['vehicle-types'].id
    for query in (
        'UPDATE vehicle_types SET requires_plate=0 WHERE id=:id',
        "UPDATE vehicle_types SET code_prefix='bad' WHERE id=:id",
        'UPDATE vehicle_types SET requires_plate=7 WHERE id=:id',
    ):
        with pytest.raises(IntegrityError):
            db_session.execute(text(query), {'id': identity})
        db_session.rollback()
