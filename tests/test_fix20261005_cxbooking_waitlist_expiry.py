from datetime import timedelta
from core.clock import BUSINESS_TZ
from test_expansion_sites import env  # noqa: F401

def test_ended_waitlist_is_not_a_live_request(env):
    response=env.client.post(f'/api/v2/sites/{env.a.id}/waitlist',json={'site_id':env.a.id,'vehicle_id':env.vehicle.id,
        'start_at':env.now.replace(tzinfo=BUSINESS_TZ).isoformat(),
        'end_at':(env.now+timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ).isoformat(), 'request_id':'waitlist-expiry-0001'})
    assert response.status_code == 201,response.text
    env.clock['now']=env.now+timedelta(hours=2)
    base=f'/api/v2/sites/{env.a.id}/waitlist'
    assert env.client.get(base,params={'status':'waiting'}).json() == []
    assert env.client.get(base).json()[0]['status'] == 'expired'
    env.actor['user']=env.account
    assert env.client.get('/api/v2/me/waitlist',params={'status':'waiting'}).json() == []
    assert env.client.get('/api/v2/me/waitlist').json()[0]['status'] == 'expired'
