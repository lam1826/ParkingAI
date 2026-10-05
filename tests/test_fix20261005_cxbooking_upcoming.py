from datetime import timedelta
from sqlalchemy import select
from test_expansion_sites import env, data
from expansion import reservations as service
from expansion.portal_models import PortalNotification
from expansion.site_schemas import BookingWindow


def test_future_waitlist_offer_names_vehicle_site_slot_and_local_arrival_window(env):
    window = data(env).model_dump(exclude={'slot_id'})
    window['start_at'] += timedelta(days=2)
    window['end_at'] += timedelta(days=2)
    row = service.join_waitlist(env.db, env.staff, BookingWindow(**window))
    offered = service.offer_waitlist(env.db, env.staff, row)
    env.db.commit()
    notification = env.db.scalar(select(PortalNotification).where(
        PortalNotification.event_key == f'waitlist:{row.id}:offered'))
    for value in (env.vehicle.license_plate, env.a.name, env.slot.slot_name,
                  offered.start_at.strftime('%d/%m/%Y %H:%M'),
                  offered.arrival_deadline.strftime('%d/%m/%Y %H:%M')):
        assert value in notification.message
    assert '15 phút sau giờ hẹn' in notification.message
    assert '+07:00' not in notification.message
    # Customer sees the offered booking outside history and can withdraw it.
    env.actor['user'] = env.account
    active = env.client.get('/api/v2/me/reservations', params={'site_id':env.a.id,'status':'confirmed'})
    assert active.status_code == 200, active.text
    assert any(item['id'] == offered.id and item['license_plate'] == env.vehicle.license_plate
               for item in active.json())
    cancelled = env.client.post(f'/api/v2/me/waitlist/{row.id}/cancel')
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()['status'] == 'cancelled'
