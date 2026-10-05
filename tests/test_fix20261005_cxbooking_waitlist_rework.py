from datetime import timedelta
import pytest
from test_expansion_sites import env, data
from expansion import reservations
from expansion.site_schemas import BookingWindow


@pytest.mark.parametrize('finish,status', [('arrive','used'),('deadline','expired'),('expire','expired'),('worker','expired'),('cancel','cancelled'),('live','offered')])
def test_offered_waitlist_views_only_offer_unused_unexpired_reservations(env, monkeypatch, finish, status):
    row = reservations.join_waitlist(env.db, env.staff, BookingWindow(**data(env).model_dump(exclude={'slot_id'})))
    offered = reservations.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    if finish == 'arrive':
        reservations.arrive(env.db, env.staff, offered)
    elif finish == 'cancel':
        reservations.cancel(env.db, env.staff, offered)
    elif finish in ('deadline','expire','worker'):
        env.clock['now'] = env.now + timedelta(hours=1)
        if finish == 'expire':
            reservations.expire_slot(env.db, offered.slot_id, env.clock['now'])
        elif finish == 'worker':
            import expansion.portal_worker as worker
            monkeypatch.setattr(worker, 'business_now', lambda:env.clock['now'])
            worker.run_portal_maintenance(env.db)
    env.db.commit()
    for actor,path in [(env.account,'/api/v2/me/waitlist'),(env.staff,f'/api/v2/sites/{env.a.id}/waitlist')]:
        env.actor['user'] = actor
        live = env.client.get(path,params={'status':'offered'})
        assert live.status_code == 200,live.text
        assert len(live.json()) == int(finish=='live')
        all_rows = env.client.get(path).json()
        assert next(item for item in all_rows if item['id']==row.id)['status'] == status
        matching = env.client.get(path,params={'status':status})
        assert matching.status_code == 200, matching.text
        assert any(item['id']==row.id for item in matching.json())
