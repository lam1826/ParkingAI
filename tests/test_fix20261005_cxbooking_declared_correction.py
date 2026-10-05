from datetime import timedelta

import pytest
from sqlalchemy import select

from test_expansion_sites import env  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.site_service import availability
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService


def second_slot(e):
    s2 = ParkingSlot(zone_id=e.slot.zone_id, vehicle_type_id=e.slot.vehicle_type_id, slot_name="A-02",
                     is_occupied=False, is_active=True)
    e.db.add(s2); e.db.commit()
    return s2


def check_in(e, plate):
    e.actor['user'] = e.staff
    r = e.client.post(f'/api/v2/sites/{e.a.id}/check-in', json={'license_plate': plate,
        'vehicle_type_id': e.slot.vehicle_type_id})
    assert r.status_code == 201, r.text
    return r.json()


def correct(e, sid, plate, rid='corr-0001'):
    e.actor['user'] = e.staff
    return e.client.post(f'/api/v2/sites/{e.a.id}/sessions/{sid}/correct-plate',
        json={'reason': 'Camera đọc nhầm biển số', 'request_id': rid, 'license_plate': plate})


def checkout(e, sid):
    quote = CheckoutService(e.db).quote(sid, e.staff.id)
    conf = CheckoutConfirmation(quote_token=quote['quote_token'], payment_confirmed=True,
                                payment_method='cash' if quote['parking_fee'] else None)
    CheckoutService(e.db).confirm(conf, e.staff.id, session_id=sid)


def test_b_live_declaration_not_consumed_by_correction(customer_env):
    e = customer_env
    s2 = second_slot(e)
    booking = post_booking(e)  # 51A-887.76, start now+10min
    assert booking.status_code == 201, booking.text
    bid = booking.json()['id']
    print('\nBOOKING slot', booking.json()['slot_name'], 'status', booking.json()['status'],
          'vehicles for plate', e.db.scalar(select(Vehicle.id).where(Vehicle.license_plate.like('51A%'))))
    e.clock['now'] += timedelta(minutes=11)  # driver arrives on time
    misread = check_in(e, '51A-887.75')
    sess = e.db.get(ParkingSession, misread['session_id'])
    print('MISREAD slot', e.db.get(ParkingSlot, sess.parking_slot_id).slot_name,
          'billing', sess.billing_policy_version)
    e.clock['now'] += timedelta(minutes=1)
    r = correct(e, sess.id, '51A-887.76')
    print('CORRECT status', r.status_code, r.text[:200])
    assert r.status_code == 409, r.text
    assert 'đặt trước' in r.json()['detail'].lower()
    row=e.db.get(DeclaredParkingReservation,bid);e.db.refresh(row)
    assert row.status == 'confirmed' and row.session_id is None
    assert e.db.get(ParkingSession,sess.id).status == 'active'


def test_b_control_direct_admission_consumes(customer_env):
    e = customer_env
    second_slot(e)
    bid = post_booking(e).json()['id']
    e.clock['now'] += timedelta(minutes=11)
    ok = check_in(e, '51A-887.76')
    row = e.db.get(DeclaredParkingReservation, bid); e.db.refresh(row)
    print('\nCONTROL direct admission: booking', row.status, 'session match', row.session_id == ok['session_id'])
    assert row.status == 'arrived'


def _returning_driver(e, cancel_first):
    second_slot(e)
    b = post_booking(e)
    assert b.status_code == 201, b.text
    if cancel_first:
        c = e.client.post(f"/api/v2/me/advance-bookings/{b.json()['id']}/cancel")
        assert c.status_code == 200, c.text
        print('\nDECLARATION status after cancel', c.json()['status'])
    e.clock['now'] += timedelta(minutes=11)
    walk = check_in(e, '51A-887.76')  # arrival (consumes if not cancelled) or plain walk-in
    row = e.db.get(DeclaredParkingReservation, b.json()['id']); e.db.refresh(row)
    print('FIRST VISIT booking status', row.status)
    e.clock['now'] += timedelta(hours=1)
    checkout(e, walk['session_id'])
    print('VEHICLE ROW', e.db.scalar(select(Vehicle.license_plate).where(Vehicle.license_plate.like('51A%887%76'))))
    e.clock['now'] += timedelta(days=3)
    misread = check_in(e, '51A-887.75')
    return correct(e, misread['session_id'], '51A-887.76')


def test_a_cancelled_declaration_blocks_correction(customer_env):
    r = _returning_driver(customer_env, cancel_first=True)
    print('CORRECT to returning plate with cancelled booking:', r.status_code, r.json().get('detail'))
    assert r.status_code == 200, r.text


def test_a2_completed_arrived_declaration_blocks_correction(customer_env):
    r = _returning_driver(customer_env, cancel_first=False)
    print('CORRECT to returning plate with completed (arrived) booking:', r.status_code, r.json().get('detail'))
    assert r.status_code == 409


def test_a_control_no_declaration_correction_succeeds(customer_env):
    e = customer_env
    second_slot(e)
    e.clock['now'] += timedelta(minutes=11)
    walk = check_in(e, '51A-887.76')
    e.clock['now'] += timedelta(hours=1)
    checkout(e, walk['session_id'])
    e.clock['now'] += timedelta(days=3)
    misread = check_in(e, '51A-887.75')
    r = correct(e, misread['session_id'], '51A-887.76')
    print('\nCONTROL correct to returning plate, never declared:', r.status_code)
    assert r.status_code == 200, r.text
