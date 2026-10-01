"""Known-vehicle declarations must respect live rights, not historical status."""
from datetime import timedelta

import pytest
from sqlalchemy import event

from core.clock import BUSINESS_TZ
from crud.parking_session import claim_session_for_checkout
from expansion import reservations
from expansion.site_schemas import AllocationCreate
from expansion.site_service import availability
from expansion.simplified_customer_models import DeclaredParkingReservation
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from test_expansion_sites import data, env, reserve  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401


@pytest.mark.parametrize('prior, expected', [
    ('confirmed', 409),
    ('deadline', 201),
    ('expired_no_show', 201),
    ('cancelled', 201),
    ('arrived_active', 409),
    ('checking_out', 409),
    ('departed', 201),
    ('allocation_active', 409),
    ('allocation_cancelled', 201),
])
def test_optional_booking_only_conflicts_with_live_vehicle_rights(customer_env, request, prior, expected):
    e = customer_env
    # The DB guard checks expiry against the new row's created_at. Advance that
    # default with the same test clock as the service instead of wall-clock time.
    def timestamp(_mapper, _connection, row):
        row.created_at = e.clock['now']

    event.listen(DeclaredParkingReservation, 'before_insert', timestamp)
    request.addfinalizer(lambda: event.remove(DeclaredParkingReservation, 'before_insert', timestamp))
    # A free alternate slot makes the vehicle commitment check observable even
    # when the old slot is reserved or occupied. Never weaken physical capacity.
    e.slot.zone.capacity += 1
    e.db.add(ParkingSlot(zone_id=e.slot.zone_id, vehicle_type_id=e.vehicle.vehicle_type_id,
                         slot_name='LIFECYCLE-ALTERNATE'))
    e.db.commit()
    if prior.startswith('allocation_'):
        old = reservations.reserve(e.db, e.staff, AllocationCreate(**data(e).model_dump()), allocation=True)
        e.db.commit()
        if prior == 'allocation_cancelled':
            reservations.cancel(e.db, e.staff, old)
            e.db.commit()
    else:
        old = reserve(e)
        if prior in {'arrived_active', 'checking_out', 'departed'}:
            reservations.arrive(e.db, e.staff, old)
            e.db.commit()
            e.clock['now'] += timedelta(minutes=1)
            checkout = CheckoutService(e.db)
            if prior == 'departed':
                quote = checkout.quote(old.session_id, e.staff.id)
                checkout.confirm(CheckoutConfirmation(quote_token=quote['quote_token'],
                    payment_confirmed=True, payment_method='cash'), e.staff.id)
                assert e.db.get(ParkingSession, old.session_id).status == 'completed'
            elif prior == 'checking_out':
                # A quote is read-only. Exercise the actual transitional claim
                # without committing an incomplete checkout into the fixture.
                assert claim_session_for_checkout(e.db, old.session_id)
                assert e.db.get(ParkingSession, old.session_id).status == 'checking_out'
        elif prior in {'deadline', 'expired_no_show'}:
            e.clock['now'] = old.arrival_deadline + timedelta(seconds=prior != 'deadline')
            # Reading availability does not run the expiry writer; this row is
            # deliberately still confirmed when the new API request arrives.
            assert old.status == 'confirmed'
        elif prior == 'cancelled':
            reservations.cancel(e.db, e.staff, old)
            e.db.commit()

    old_status, old_session = old.status, getattr(old, 'session_id', None)
    assert availability(e.db, e.a.id)['available_now'] >= 1
    response = post_booking(e, license_plate=e.vehicle.license_plate,
        start_at=(e.clock['now'] + timedelta(minutes=1)).replace(tzinfo=BUSINESS_TZ).isoformat(),
        end_at=(e.clock['now'] + timedelta(minutes=30)).replace(tzinfo=BUSINESS_TZ).isoformat())
    assert response.status_code == expected, response.text
    e.db.refresh(old)
    assert old.status == old_status
    assert getattr(old, 'session_id', None) == old_session
    if expected == 409:
        assert response.json()['detail'] == 'Xe đã có cam kết chỗ trong khoảng này; hãy kiểm tra đặt chỗ hiện có.'
