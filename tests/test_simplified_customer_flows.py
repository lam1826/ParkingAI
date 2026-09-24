"""Real server seams on disposable SQLite; no bank, provider or application DB."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ
from expansion import declared_bookings, ticket_payment_access
from expansion.portal_models import PortalAccountLink, PortalSessionGrant, PortalVehicleOwnership
from expansion.portal_router import router as portal_router
from expansion.session_payment_router import router as payment_router
from expansion.simplified_customer_models import DeclaredParkingReservation, SessionPaymentAccess
from expansion.simplified_customer_router import router
from expansion.site_service import availability
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from services.parking_service import ParkingService
from services.ticket_service import get_ticket
from test_expansion_sites import env  # noqa: F401


@pytest.fixture
def customer_env(env, monkeypatch):
    env.client.app.include_router(router, prefix='/api/v2')
    env.client.app.include_router(payment_router, prefix='/api/v2')
    env.client.app.include_router(portal_router, prefix='/api/v2')
    monkeypatch.setattr(declared_bookings, 'server_now', lambda: env.clock['now'])
    monkeypatch.setattr(ticket_payment_access, 'business_now', lambda: env.clock['now'])
    env.actor['user'] = env.stranger
    env.db.execute(delete(PortalAccountLink).where(PortalAccountLink.user_id == env.stranger.id))
    env.db.commit()
    return env


def booking_body(e, **changes):
    return {'site_id': e.a.id, 'license_plate': '51A-887.76', 'vehicle_type_id': e.slot.vehicle_type_id,
        'start_at': (e.now + timedelta(minutes=10)).replace(tzinfo=BUSINESS_TZ).isoformat(),
        'end_at': (e.now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ).isoformat(),
        'request_id': 'declared-booking-test-01', **changes}


def post_booking(e, **changes):
    return e.client.post('/api/v2/me/advance-bookings', json=booking_body(e, **changes))


def admit(e, plate='51A-887.76'):
    return ParkingService(e.db).check_in(plate, e.slot.vehicle_type_id, e.staff.id,
        parking_slot_id=e.slot.id, _expected_site_id=e.a.id)


def lookup(e, plate='51A-887.76', **changes):
    return e.client.post('/api/v2/me/fee-lookup', json={'site_id': e.a.id, 'license_plate': plate,
        'vehicle_type_id': e.slot.vehicle_type_id, **changes})


def test_declared_booking_does_not_create_owner_vehicle_or_customer(customer_env):
    e = customer_env
    before = e.db.scalar(select(func.count()).select_from(Vehicle))
    first = post_booking(e)
    assert first.status_code == 201, first.text
    assert post_booking(e).json()['id'] == first.json()['id']
    assert e.db.scalar(select(func.count()).select_from(Vehicle)) == before
    assert e.db.scalar(select(PortalAccountLink).where(PortalAccountLink.user_id == e.stranger.id)) is None
    assert availability(e.db, e.a.id)['available_now'] == 0
    assert availability(e.db, e.a.id)['reserved_slots'] == 1
    conflict = post_booking(e, end_at=(e.now + timedelta(hours=3)).replace(tzinfo=BUSINESS_TZ).isoformat())
    assert conflict.status_code == 409
    assert len(e.client.get('/api/v2/me/advance-bookings').json()['items']) == 1
    e.actor['user'] = e.account
    assert e.client.get('/api/v2/me/advance-bookings').json()['items'] == []
    assert e.client.post(f"/api/v2/me/advance-bookings/{first.json()['id']}/cancel").status_code == 404


def test_only_customers_create_optional_bookings_and_cancel_releases_capacity(customer_env):
    e = customer_env
    e.actor['user'] = e.staff
    assert post_booking(e).status_code == 403
    e.actor['user'] = e.stranger
    row = post_booking(e).json()
    endpoint = f"/api/v2/me/advance-bookings/{row['id']}/cancel"
    assert e.client.post(endpoint).status_code == 200
    assert e.client.post(endpoint).status_code == 200
    assert availability(e.db, e.a.id)['available_now'] == 1


def test_declared_hold_blocks_walkin_then_matching_arrival_consumes_atomically(customer_env):
    e = customer_env
    row = post_booking(e).json()
    e.actor['user'] = e.staff
    denied = e.client.post(f'/api/v2/sites/{e.a.id}/check-in', json={'license_plate': '51A-000.01',
        'vehicle_type_id': e.slot.vehicle_type_id})
    assert denied.status_code in (404, 409), denied.text
    e.clock['now'] += timedelta(minutes=10)
    arrival = e.client.post(f'/api/v2/sites/{e.a.id}/check-in', json={'license_plate': row['license_plate'],
        'vehicle_type_id': e.slot.vehicle_type_id})
    assert arrival.status_code == 201, arrival.text
    booking = e.db.get(DeclaredParkingReservation, row['id'])
    assert booking.status == 'arrived'
    assert booking.session_id is not None
    assert e.db.get(PortalSessionGrant, booking.session_id) is None
    assert e.db.get(Vehicle, e.db.get(ParkingSession, booking.session_id).vehicle_id).customer_id is None
    assert availability(e.db, e.a.id)['occupied'] == 1
    from services.session_exception_service import SessionExceptionService
    from schemas.session_exception import SessionExceptionRequest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        SessionExceptionService(e.db).apply(e.staff, e.a.id, booking.session_id,
            SessionExceptionRequest(reason='Không được hủy cam kết âm thầm', request_id='declared-cancel-session-01'), 'cancelled')
    assert exc.value.status_code == 409
    with pytest.raises(IntegrityError, match='declared booking arrival'):
        e.db.execute(text("UPDATE parking_sessions SET status='cancelled' WHERE id=:id"), {'id': booking.session_id})
    e.db.rollback()


def test_expired_declared_hold_no_longer_counts_available_or_accepts_cancel(customer_env):
    e = customer_env
    row = post_booking(e).json()
    e.clock['now'] += timedelta(minutes=25)
    assert availability(e.db, e.a.id)['available_now'] == 1
    assert e.client.get('/api/v2/me/advance-bookings').json()['items'][0]['status'] == 'expired'
    assert e.client.post(f"/api/v2/me/advance-bookings/{row['id']}/cancel").status_code == 409


def test_declared_arrival_uses_one_instant_across_deadline(customer_env, monkeypatch):
    from crud import parking_session as session_crud

    e = customer_env
    response = post_booking(e)
    assert response.status_code == 201, response.text
    booking_id = response.json()['id']
    arrival_at = e.now + timedelta(minutes=10)
    calls = []

    def advancing_clock():
        # A second sample would cross the 15-minute arrival grace period.
        instant = arrival_at if not calls else e.now + timedelta(minutes=30)
        calls.append(instant)
        return instant

    monkeypatch.setattr(session_crud, 'server_now', advancing_clock)
    e.actor['user'] = e.staff
    entered = e.client.post(f'/api/v2/sites/{e.a.id}/check-in', json={
        'license_plate': response.json()['license_plate'],
        'vehicle_type_id': e.slot.vehicle_type_id,
    })
    assert entered.status_code == 201, entered.text
    booking = e.db.get(DeclaredParkingReservation, booking_id)
    e.db.refresh(booking)
    assert booking.status == 'arrived'
    assert booking.session_id == entered.json()['session_id']
    assert e.db.get(ParkingSession, booking.session_id).check_in_time == arrival_at
    assert calls == [arrival_at]


def test_fee_lookup_generic_failure_no_history_and_ticket_grant_current_only(customer_env):
    e = customer_env
    result = admit(e)
    session_id = result['session_id']
    existing = lookup(e)
    absent = lookup(e, '51A-000.00')
    assert existing.status_code == absent.status_code == 404
    assert existing.json() == absent.json()
    assert e.client.get(f'/api/v2/me/sessions/{session_id}/payment-status').status_code == 404
    ticket = get_ticket(e.db, session_id)
    assert ticket['payment_access_code'].startswith('PAP1.')
    assert lookup(e, ticket_proof=ticket['qr_payload']).status_code == 404, 'staff PA1 is not customer authority'
    assert lookup(e, ticket_proof='mã giả').status_code == 404
    proved = lookup(e, ticket_proof=ticket['payment_access_code'])
    assert proved.status_code == 200, proved.text
    assert proved.json()['access']['kind'] == 'ticket'
    assert proved.json()['payment_status']['gross_fee'] > 0
    assert e.db.get(PortalSessionGrant, session_id) is None
    assert e.db.scalar(select(PortalVehicleOwnership).where(PortalVehicleOwnership.vehicle_id == e.db.get(ParkingSession, session_id).vehicle_id)) is None
    assert e.client.get(f'/api/v2/me/sessions/{session_id}/payment-status').status_code == 200
    assert e.client.get('/api/v2/me/sessions').status_code == 409, 'proof does not link profile or expose history'
    assert e.client.get('/api/v2/me/receipts').json()['items'] == []
    e.actor['user'] = e.account
    assert e.client.get(f'/api/v2/me/sessions/{session_id}/payment-status').status_code == 404


def test_ticket_rotation_revokes_old_proof_and_grants(customer_env):
    e = customer_env
    identity = admit(e)['session_id']
    code = get_ticket(e.db, identity)['payment_access_code']
    assert lookup(e, ticket_proof=code).status_code == 200
    e.actor['user'] = e.staff
    response = e.client.post(f'/api/v2/sites/{e.a.id}/sessions/{identity}/ticket-payment-code/rotate')
    assert response.status_code == 200, response.text
    replacement = response.json()['payment_access_code']
    assert replacement != code
    e.actor['user'] = e.stranger
    assert e.client.get(f'/api/v2/me/sessions/{identity}/payment-status').status_code == 404
    assert lookup(e, ticket_proof=code).status_code == 404
    assert lookup(e, ticket_proof=replacement).status_code == 200


def test_ticket_access_expires_and_owner_change_invalidates(customer_env):
    e = customer_env
    identity = admit(e)['session_id']
    code = get_ticket(e.db, identity)['payment_access_code']
    assert lookup(e, ticket_proof=code).status_code == 200
    access = e.db.scalar(select(SessionPaymentAccess).where(SessionPaymentAccess.session_id == identity))
    e.clock['now'] = access.expires_at
    assert e.client.get(f'/api/v2/me/sessions/{identity}/payment-status').status_code == 404
    e.clock['now'] = e.now
    vehicle = e.db.get(Vehicle, e.db.get(ParkingSession, identity).vehicle_id)
    vehicle.customer_id = e.customer.id
    e.db.commit()
    assert e.client.get(f'/api/v2/me/sessions/{identity}/payment-status').status_code == 404
    assert lookup(e, ticket_proof=code).status_code == 404, 'an ownership change must not let the old proof re-grant access'


def test_lost_ticket_incident_revokes_payment_code_inside_its_transaction(customer_env):
    e = customer_env
    identity = admit(e)['session_id']
    proof = get_ticket(e.db, identity)['payment_access_code']
    assert lookup(e, ticket_proof=proof).status_code == 200
    from services.session_exception_service import SessionExceptionService
    from schemas.session_exception import SessionExceptionRequest
    SessionExceptionService(e.db).apply(e.staff, e.a.id, identity,
        SessionExceptionRequest(reason='Khách báo đã mất vé cũ', request_id='lost-ticket-access-01'), 'lost_ticket')
    assert lookup(e, ticket_proof=proof).status_code == 404
    assert get_ticket(e.db, identity)['payment_access_code'] is None


def test_reception_scope_and_effective_expiry_filters(customer_env):
    e = customer_env
    assert post_booking(e).status_code == 201
    path = f'/api/v2/sites/{e.a.id}/advance-bookings'
    assert e.client.get(path).status_code == 403
    e.actor['user'] = e.staff
    response = e.client.get(path, params={'status': 'confirmed'})
    assert response.status_code == 200 and response.json()['total'] == 1
    assert response.json()['items'][0]['user_id'] == e.stranger.id
    assert e.client.get(f'/api/v2/sites/{e.b.id}/advance-bookings').status_code == 403
    e.clock['now'] += timedelta(minutes=25)
    assert e.client.get(path, params={'status': 'confirmed'}).json()['total'] == 0
    assert e.client.get(path, params={'status': 'expired'}).json()['items'][0]['status'] == 'expired'


def test_owned_fee_lookup_needs_no_ticket_and_cross_site_stays_private(customer_env):
    e = customer_env
    identity = admit(e, e.vehicle.license_plate)['session_id']
    e.actor['user'] = e.account
    response = lookup(e, e.vehicle.license_plate)
    assert response.status_code == 200, response.text
    assert response.json()['access']['kind'] == 'owned'
    assert lookup(e, e.vehicle.license_plate, site_id=e.b.id).status_code == 404
    assert response.json()['session']['id'] == identity


def test_fee_lookup_throttle_persists_attempts_without_secrets(customer_env):
    e = customer_env
    for _ in range(30):
        assert lookup(e, ticket_proof='do-not-store-this').status_code == 404
    response = lookup(e)
    assert response.status_code == 429
    assert response.headers['retry-after'] == '900'
    assert 'do-not-store-this' not in str(e.db.execute(text('SELECT * FROM audit_logs')).all())


def test_declared_db_guard_preserves_history_and_blocks_slot_deactivation(customer_env):
    e = customer_env
    row = post_booking(e).json()
    for query, params in (
        ('DELETE FROM declared_parking_reservations WHERE id=:id', {'id': row['id']}),
        ('UPDATE parking_slots SET is_active=0 WHERE id=:id', {'id': e.slot.id}),
        ('UPDATE declared_parking_reservations SET license_plate=:plate WHERE id=:id', {'id': row['id'], 'plate': '51A11111'}),
    ):
        with pytest.raises(IntegrityError):
            e.db.execute(text(query), params)
        e.db.rollback()


def test_unplated_admission_and_booking_generate_codes_no_fake_license(customer_env):
    e = customer_env
    # Use a fresh type; an existing type with vehicle history is deliberately immutable.
    from models.vehicle_type import VehicleType
    from models.price_config import PriceConfig
    kind = VehicleType(name='Xe đạp mã tự động', requires_plate=False, code_prefix='BIKECODE', is_active=True)
    e.db.add(kind); e.db.flush()
    e.slot.vehicle_type_id = kind.id
    e.db.add(PriceConfig(vehicle_type_id=kind.id, ticket_type='HOURLY', price=2000, effective_date=e.now.date(), is_active=True))
    e.db.commit()
    response = post_booking(e, license_plate='', vehicle_type_id=kind.id)
    assert response.status_code == 201, response.text
    assert response.json()['license_plate'].startswith('BIKECODE-')
    assert post_booking(e, license_plate='', vehicle_type_id=kind.id).json()['id'] == response.json()['id']
    e.client.post(f"/api/v2/me/advance-bookings/{response.json()['id']}/cancel")
    e.actor['user'] = e.staff
    result = e.client.post(f'/api/v2/sites/{e.a.id}/check-in', json={'vehicle_type_id': kind.id})
    assert result.status_code == 201, result.text
    assert result.json()['license_plate'].startswith('BIKECODE-')
    from routers.parking import router as legacy_parking_router
    e.client.app.include_router(legacy_parking_router)
    from services.checkout_service import CheckoutService
    quote = CheckoutService(e.db).quote(result.json()['session_id'], e.staff.id)
    exit_result = e.client.post('/parking/check-out', json={'license_plate': result.json()['license_plate'],
        'quote_token': quote['quote_token'], 'payment_confirmed': True,
        'payment_method': 'transfer' if quote['balance_due'] > 0 else None})
    assert exit_result.status_code == 200, exit_result.text
