"""Canonical correction preserves vehicle identity and ownership guards."""
import pytest
from sqlalchemy import select, func
from test_session_exceptions import env, body  # noqa: F401
from models.vehicle import Vehicle
from models.parking_session import ParkingSession
from services.parking_service import ParkingService

@pytest.mark.parametrize('bound,parked', [(False,False),(True,False),(False,True)])
def test_correction_resolves_plate_variant(env, customer, bound, parked):
    target = Vehicle(license_plate='59A-777.77', vehicle_type_id=env.vehicle.vehicle_type_id,
        customer_id=customer.id if bound else None)
    env.db.add(target); env.db.commit()
    if parked:
        from models.parking_slot import ParkingSlot
        slot = ParkingSlot(zone_id=env.slot.zone_id, vehicle_type_id=target.vehicle_type_id,slot_name='A-02')
        env.db.add(slot); env.db.commit()
        ParkingService(env.db).check_in(target.license_plate, target.vehicle_type_id,env.staff.id,parking_slot_id=slot.id)
    response = env.client.post(env.base+'/correct-plate',json=body(license_plate='59A77777'))
    assert response.status_code == (409 if bound or parked else 200), response.text
    assert env.db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.license_plate.in_(['59A77777','59A-777.77']))) == 1
    if not bound and not parked:
        assert env.db.get(ParkingSession,response.json()['replacement_session_id']).vehicle_id == target.id

def test_correction_cannot_respell_original(env):
    response = env.client.post(env.base+'/correct-plate',json=body(license_plate='30A99999'))
    assert response.status_code == 422, response.text
