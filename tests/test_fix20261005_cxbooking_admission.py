from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from core.clock import BUSINESS_TZ, business_now
from crud import parking_session as session_crud
from expansion import reservations as service
from expansion.reservations import admission_allowed
from expansion.simplified_customer_models import DeclaredParkingReservation as Booking
from expansion.simplified_customer_router import router as declared_router
from expansion.site_schemas import ReservationCreate
from expansion.timed_parking_models import TimedParkingPass
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from services.parking_service import ParkingService
import services.parking_service as ps
from test_expansion_sites import env  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_timed_parking import timed, purchase  # noqa: F401


def iso(v):
    return v.replace(tzinfo=BUSINESS_TZ).isoformat()


def spy_db_errors(monkeypatch):
    seen = []
    orig = ps.map_check_in_integrity_error
    def spy(exc):
        seen.append(str(exc.orig))
        return orig(exc)
    monkeypatch.setattr(ps, 'map_check_in_integrity_error', spy)
    return seen


def add_second_slot(e):
    e.slot.zone.capacity += 1
    extra = ParkingSlot(zone_id=e.slot.zone_id, vehicle_type_id=e.vehicle.vehicle_type_id, slot_name='A-02')
    e.db.add(extra)
    e.db.commit()
    return extra


@pytest.mark.parametrize('later_days', [None, 1, 29])
def test_declared_holder_vs_later_declared_same_slot(customer_env, monkeypatch, later_days):
    e = customer_env
    extra = add_second_slot(e)
    first = post_booking(e, license_plate='51H-11111', start_at=iso(e.now + timedelta(minutes=10)),
                         end_at=iso(e.now + timedelta(hours=1, minutes=10)), request_id='verify-first-000001')
    assert first.status_code == 201, first.text
    print(f'\n[later_days={later_days}] booking A ->', first.status_code, first.json()['slot_name'])
    if later_days is not None:
        e.actor['user'] = e.account
        second = post_booking(e, license_plate='51H-22222', start_at=iso(e.now + timedelta(days=later_days)),
                              end_at=iso(e.now + timedelta(days=later_days, hours=1)), request_id='verify-second-00001')
        assert second.status_code == 201, second.text
        print(f'[later_days={later_days}] booking B ->', second.status_code, second.json()['slot_name'],
              'start', second.json()['start_at'])
        assert second.json()['slot_id'] == first.json()['slot_id']
    e.clock['now'] = e.now + timedelta(minutes=11)
    seen = spy_db_errors(monkeypatch)
    e.actor['user'] = e.staff
    # app-level predicate for the vehicle that will be created on admission: emulate with no vehicle
    # (vehicle row does not yet exist); real admission computes it after creating the vehicle.
    r = e.client.post(f'/api/v2/sites/{e.a.id}/check-in',
                      json={'license_plate': '51H-11111', 'vehicle_type_id': e.vehicle.vehicle_type_id})
    print(f'[later_days={later_days}] staff auto check-in ->', r.status_code, r.json(), '| DB errors:', seen)
    if later_days is None:
        assert r.status_code == 201
        assert r.json()['slot_name'] == first.json()['slot_name']
        return
    assert r.status_code == 201, r.text
    assert not seen


def test_reservation_arrive_api_vs_later_declared(customer_env, monkeypatch):
    e = customer_env
    start, end = e.now + timedelta(minutes=5), e.now + timedelta(hours=2)
    row = service.reserve(e.db, e.staff, ReservationCreate(site_id=e.a.id, vehicle_id=e.vehicle.id,
        start_at=start.replace(tzinfo=BUSINESS_TZ), end_at=end.replace(tzinfo=BUSINESS_TZ),
        request_id='verify-formal-res-01'))
    e.db.commit()
    e.actor['user'] = e.stranger
    later = post_booking(e, license_plate='51G-55555', start_at=iso(e.now + timedelta(days=1)),
                         end_at=iso(e.now + timedelta(days=1, hours=1)), request_id='verify-declared-tmrw')
    assert later.status_code == 201, later.text
    print('\nreservation slot', row.slot_id, '| later declared ->', later.status_code, later.json()['slot_id'])
    e.clock['now'] = start + timedelta(minutes=1)
    allowed = admission_allowed(e.db, row.slot_id, vehicle_id=e.vehicle.id, at=e.clock['now'], lock=False)
    print('app admission_allowed for reserved vehicle:', allowed)
    seen = spy_db_errors(monkeypatch)
    e.actor['user'] = e.staff
    r = e.client.post(f'/api/v2/sites/{e.a.id}/reservations/{row.id}/arrive')
    print('POST arrive ->', r.status_code, r.json(), '| DB errors:', seen)
    assert allowed is True
    assert r.status_code == 200, r.text
    assert not seen


def test_reservation_arrive_api_control_without_later_declared(customer_env, monkeypatch):
    e = customer_env
    start, end = e.now + timedelta(minutes=5), e.now + timedelta(hours=2)
    row = service.reserve(e.db, e.staff, ReservationCreate(site_id=e.a.id, vehicle_id=e.vehicle.id,
        start_at=start.replace(tzinfo=BUSINESS_TZ), end_at=end.replace(tzinfo=BUSINESS_TZ),
        request_id='verify-formal-res-02'))
    e.db.commit()
    e.clock['now'] = start + timedelta(minutes=1)
    e.actor['user'] = e.staff
    r = e.client.post(f'/api/v2/sites/{e.a.id}/reservations/{row.id}/arrive')
    print('\ncontrol POST arrive ->', r.status_code, r.json().get('status'))
    assert r.status_code == 200 and r.json()['status'] == 'arrived'


def test_paid_ticket_vs_later_declared(timed, monkeypatch):
    portal_, body, slot, rate = timed
    client, current, users, site, kind, db = portal_
    client.app.include_router(declared_router, prefix='/api/v2')
    order = purchase(timed)
    print('\npaid ticket', order['status'], order['slot']['name'], order['entitlement_status'])
    current['user'] = users[2]
    tomorrow = business_now() + timedelta(days=1)
    d = client.post('/api/v2/me/advance-bookings', json={'site_id': site.id, 'license_plate': '51K-88888',
        'vehicle_type_id': kind.id, 'start_at': iso(tomorrow), 'end_at': iso(tomorrow + timedelta(hours=1)),
        'request_id': 'verify-declared-tmrw-2'})
    print('declared tomorrow', d.status_code, d.json().get('slot_name'))
    assert d.status_code == 201
    ticket = db.get(TimedParkingPass, order['timed_pass_id'])
    monkeypatch.setattr(session_crud, 'server_now', lambda: ticket.start_at + timedelta(minutes=1))
    vehicle = db.get(Vehicle, body['vehicle_id'])
    allowed = admission_allowed(db, slot.id, vehicle_id=vehicle.id, at=ticket.start_at + timedelta(minutes=1), lock=False)
    print('app admission_allowed for ticket holder:', allowed)
    seen = spy_db_errors(monkeypatch)
    result = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    assert result["session_id"]
    assert not seen


def test_allocation_holder_vs_later_declared(customer_env, monkeypatch):
    e = customer_env
    start, end = e.now + timedelta(minutes=5), e.now + timedelta(hours=2)
    alloc = service.reserve(e.db, e.staff, ReservationCreate(site_id=e.a.id, vehicle_id=e.vehicle.id,
        start_at=start.replace(tzinfo=BUSINESS_TZ), end_at=end.replace(tzinfo=BUSINESS_TZ),
        request_id='verify-allocation-01'), allocation=True)
    e.db.commit()
    e.actor['user'] = e.stranger
    later = post_booking(e, license_plate='51G-77777', start_at=iso(e.now + timedelta(days=2)),
                         end_at=iso(e.now + timedelta(days=2, hours=1)), request_id='verify-declared-alloc')
    assert later.status_code == 201, later.text
    print('\nallocation slot', alloc.slot_id, '| later declared ->', later.status_code, later.json()['slot_id'])
    e.clock['now'] = start + timedelta(minutes=1)
    allowed = admission_allowed(e.db, alloc.slot_id, vehicle_id=e.vehicle.id, at=e.clock['now'], lock=False)
    print('app admission_allowed for allocation holder:', allowed)
    seen = spy_db_errors(monkeypatch)
    e.actor['user'] = e.staff
    r = e.client.post(f'/api/v2/sites/{e.a.id}/check-in', json={'license_plate': e.vehicle.license_plate,
        'vehicle_type_id': e.vehicle.vehicle_type_id, 'parking_slot_id': alloc.slot_id})
    print('allocation holder check-in ->', r.status_code, r.json(), '| DB errors:', seen)
    assert allowed is True
    assert r.status_code == 201, r.text
    assert not seen


@pytest.mark.parametrize("message", ["slot has declared booking", "slot has a live payment hold"])
def test_last_moment_capacity_backstops_return_conflict_not_internal_error(env, message):
    from sqlalchemy import text
    # The application sees an empty slot; simulate the backstop discovering
    # a commitment at the final insert, after its optimistic admission checks.
    env.db.execute(text("CREATE TRIGGER test_late_capacity BEFORE INSERT ON parking_sessions "
                        f"BEGIN SELECT RAISE(ABORT, '{message}'); END"))
    env.db.commit()
    env.actor['user'] = env.staff
    response = env.client.post(f'/api/v2/sites/{env.a.id}/check-in', json={
        'license_plate':'51H99999', 'vehicle_type_id':env.vehicle.vehicle_type_id})
    assert response.status_code == 409, response.text
    assert 'đặt chỗ' in response.json()['detail']
    assert env.db.scalar(select(ParkingSession.id)) is None
