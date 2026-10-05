from datetime import timedelta
from test_expansion_sites import env  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
import pytest

@pytest.mark.parametrize('extra', [False,True])
def test_early_reception_has_clear_conflict(customer_env, extra):
    e=customer_env
    if extra:
        e.slot.zone.capacity += 1
        e.db.add(ParkingSlot(zone_id=e.slot.zone_id,vehicle_type_id=e.slot.vehicle_type_id,slot_name='EARLY-ALT'));e.db.commit()
    booking=post_booking(e).json();e.actor['user']=e.staff
    response=e.client.post(f'/api/v2/sites/{e.a.id}/check-in',json={'license_plate':booking['license_plate'],'vehicle_type_id':booking['vehicle_type_id'],'declared_booking_id':booking['id']})
    assert response.status_code == 409, response.text
    assert 'chưa đến giờ' in response.json()['detail']
    assert e.db.query(ParkingSession).count() == 0
    e.clock['now']=e.now+timedelta(minutes=10)
    response=e.client.post(f'/api/v2/sites/{e.a.id}/check-in',json={'license_plate':booking['license_plate'],'vehicle_type_id':booking['vehicle_type_id'],'declared_booking_id':booking['id']})
    assert response.status_code == 201,response.text
