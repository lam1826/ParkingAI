"""#29 fix: a legacy-stored plate must not make every other vehicle edit fail."""
import pytest
from models.vehicle import Vehicle
from test_core_crud_permissions import core_access  # noqa: F401


@pytest.mark.parametrize("plate", ["29MĐ1-123.45", "29mđ1-123.45", "30A-123.45"])
def test_unchanged_legacy_plate_edit(client, db_session, core_access, plate):
    headers = core_access["headers"]["staff"]
    legacy = Vehicle(license_plate=plate.replace("30A-123.45", "30A-123.47"), vehicle_type_id=core_access["vehicle-types"].id)
    db_session.add(legacy); db_session.commit()
    payload = {"license_plate": legacy.license_plate.strip().upper(), "vehicle_type_id": legacy.vehicle_type_id,
               "customer_id": core_access["customers"].id}  # exactly what VehicleDialog sends
    response = client.put(f"/api/v1/vehicles/{legacy.id}", headers=headers, json=payload)
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('plate',['29MĐ1-123.45','30A\u2013123.45','30A/12345','30A\u00a012345'])
def test_changed_plate_must_still_be_admittable(client, core_access, plate):
    response=client.put(f"/api/v1/vehicles/{core_access['vehicles'].id}",
        headers=core_access['headers']['staff'],json={'license_plate':plate})
    assert response.status_code == 422,response.text


def test_unchanged_legacy_plate_with_completed_history_keeps_identity(client, db_session, core_access):
    from datetime import timedelta
    from sqlalchemy import select
    from core.clock import business_now
    from models.parking_session import ParkingSession
    from models.user import User
    legacy=Vehicle(license_plate='29mđ1-123.45',vehicle_type_id=core_access['vehicle-types'].id)
    db_session.add(legacy);db_session.flush()
    staff=db_session.scalar(select(User).where(User.username=='core_staff'))
    now=business_now()
    history=ParkingSession(vehicle_id=legacy.id,check_in_time=now-timedelta(hours=1),check_out_time=now,
        status='completed',parking_fee=0,staff_in_id=staff.id,staff_out_id=staff.id)
    db_session.add(history);db_session.commit()
    response=client.put(f'/api/v1/vehicles/{legacy.id}',headers=core_access['headers']['staff'],
        json={'license_plate':legacy.license_plate.upper(),'vehicle_type_id':legacy.vehicle_type_id,'customer_id':core_access['customers'].id})
    assert response.status_code==200,response.text
    db_session.refresh(legacy);db_session.refresh(history)
    assert legacy.license_plate=='29mđ1-123.45'
    assert history.vehicle_id==legacy.id and history.status=='completed'
