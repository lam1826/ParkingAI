from datetime import timedelta
import pytest
from core.clock import BUSINESS_TZ
from test_expansion_sites import env  # noqa: F401

@pytest.mark.parametrize('resource',['reservations','allocations','waitlist'])
def test_booking_list_identifies_vehicle(env,resource):
    base=f'/api/v2/sites/{env.a.id}/{resource}'
    response=env.client.post(base,json={'site_id':env.a.id,'vehicle_id':env.vehicle.id,
        **({'slot_id':env.slot.id} if resource=='allocations' else {}),
        'start_at':(env.now+timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ).isoformat(),
        'end_at':(env.now+timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ).isoformat(),'request_id':'booking-label-0001-'+resource})
    assert response.status_code == 201,response.text
    rows=env.client.get(base).json()
    assert rows[0]['license_plate'] == env.vehicle.license_plate
