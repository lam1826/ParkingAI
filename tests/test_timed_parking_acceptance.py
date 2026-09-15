"""Independent P4 acceptance: purchased terms, actual departure and money history."""
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from core.clock import BUSINESS_TZ, business_now
from expansion.portal_models import PortalOrder
from expansion.site_models import ParkingReservation
from expansion.timed_parking_models import TimedParkingPass
from models.parking_session import ParkingSession
from models.payment import Payment
from models.vehicle import Vehicle
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from services.payment_service import PaymentService
from test_portal_api import portal
from test_timed_parking import timed, purchase


def arrive(timed, order, monkeypatch, *, late_seconds=0):
    context, body, slot, _rate = timed
    _client, _current, users, _site, kind, db = context
    ticket = db.get(TimedParkingPass, order['timed_pass_id'])
    at = ticket.start_at + timedelta(seconds=late_seconds)
    monkeypatch.setattr('crud.parking_session.server_now', lambda: at)
    vehicle = db.get(Vehicle, body['vehicle_id'])
    result = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    return db.get(ParkingSession, result['session_id']), ticket


def test_purchased_window_and_price_survive_plan_and_tariff_edits(timed, monkeypatch):
    context, body, slot, rate = timed
    client, current, users, _site, _kind, db = context
    response = client.post('/api/v2/me/orders', json=body)
    assert response.status_code == 200, response.text
    pending = response.json()
    current['user'] = users[0]
    edited = client.patch(f"/api/v2/portal/admin/plans/{body['plan_id']}",
        json={'name': 'Changed after purchase', 'price': 99000, 'duration_minutes': 240})
    assert edited.status_code == 200, edited.text
    rate.price = 50000
    db.commit()
    current['user'] = users[1]
    paid = client.post(f"/api/v2/me/orders/{pending['id']}/simulate",
        json={'token': pending['demo_token'], 'outcome': 'success'})
    assert paid.status_code == 200, paid.text
    order = paid.json()
    assert order['amount'] == 12000 and order['duration_minutes'] == 120
    assert order['plan_name'] == pending['plan_name']
    assert order['end_at'] == pending['end_at']
    session, ticket = arrive(timed, order, monkeypatch, late_seconds=14 * 60)
    assert session.rate_unit_price == 5000
    assert session.prepaid_end_at == ticket.end_at  # late arrival never extends the window
    monkeypatch.setattr('crud.parking_session.server_now', lambda: ticket.end_at + timedelta(seconds=1))
    quote = CheckoutService(db).quote(session.id, users[0].id)
    assert quote['parking_fee'] == 5000
    assert quote['prepaid']['amount'] == 12000


@pytest.mark.parametrize(('overstay', 'expected'), [(0, 0), (1, 5000), (3601, 10000)])
def test_manual_prepaid_checkout_collects_only_overstay_and_replays_once(timed, monkeypatch, overstay, expected):
    context, body, slot, rate = timed
    client, current, users, _site, _kind, db = context
    made = client.post('/api/v2/me/orders', json={**body, 'payment_mode': 'manual'})
    assert made.status_code == 200, made.text
    current['user'] = users[0]
    collected = client.post(f"/api/v2/portal/admin/orders/{made.json()['id']}/collect",
        json={'confirmed': True, 'payment_method': 'transfer'})
    assert collected.status_code == 200, collected.text
    order = collected.json()
    original_id = order['receipt_id']
    session, ticket = arrive(timed, order, monkeypatch)
    at = ticket.end_at + timedelta(seconds=overstay)
    monkeypatch.setattr('crud.parking_session.server_now', lambda: at)
    service = CheckoutService(db)
    quote = service.quote(session.id, users[0].id)
    assert quote['parking_fee'] == expected
    confirmation = CheckoutConfirmation(quote_token=quote['quote_token'], payment_confirmed=True,
        payment_method='transfer' if expected else None)
    completed = service.confirm(confirmation, users[0].id, session_id=session.id)
    assert completed.status == 'completed' and completed.parking_fee == expected
    assert service.confirm(confirmation, users[0].id, session_id=session.id).id == session.id
    db.refresh(slot)
    assert slot.is_occupied is False
    assert db.get(Payment, original_id).amount == 12000
    receipts = db.scalars(select(Payment).where(Payment.kind == 'receipt')).all()
    assert len(receipts) == (2 if expected else 1)
    assert sum(row.amount for row in receipts) == 12000 + expected
    revenue = PaymentService.revenue_breakdown(db, ticket.start_at - timedelta(days=1), at + timedelta(days=1))
    assert revenue['total_revenue'] == 12000 + expected


def test_daily_product_is_24_hours_across_midnight(timed):
    context, body, _slot, _rate = timed
    client, current, users, site, kind, db = context
    current['user'] = users[0]
    response = client.post('/api/v2/portal/admin/plans', json={'name': 'Một ngày', 'site_id': site.id,
        'vehicle_type_id': kind.id, 'product_kind': 'daily', 'price': 50000})
    assert response.status_code == 200, response.text
    assert response.json()['duration_minutes'] == 1440
    current['user'] = users[1]
    start = (business_now() + timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
    made = client.post('/api/v2/me/orders', json={**body, 'plan_id': response.json()['id'],
        'start_at': start.replace(tzinfo=BUSINESS_TZ).isoformat()})
    assert made.status_code == 200, made.text
    order = db.get(PortalOrder, made.json()['id'])
    assert order.end_at - order.start_at == timedelta(hours=24)
    assert order.arrival_deadline == start + timedelta(minutes=15)


def test_used_timed_pass_cannot_be_refunded_or_reassigned(timed, monkeypatch):
    context, body, slot, rate = timed
    client, current, users, _site, _kind, db = context
    order = purchase(timed)
    requested = client.post(f"/api/v2/me/orders/{order['id']}/refund-requests", json={'reason': 'Chưa dùng lúc gửi yêu cầu'})
    assert requested.status_code == 200
    session, ticket = arrive(timed, order, monkeypatch)
    current['user'] = users[0]
    response = client.post(f"/api/v2/portal/admin/refund-requests/{requested.json()['id']}/resolve",
        json={'approve': True, 'note': 'Thử hoàn sau khi vào'})
    assert response.status_code == 409, response.text
    db.refresh(ticket)
    assert ticket.status == 'consumed'
    assert db.get(ParkingSession, session.id).status == 'active'
    assert db.get(ParkingReservation, ticket.reservation_id).status == 'arrived'
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.kind == 'refund')) == 0


def test_live_timed_pass_rejects_wrong_slot_without_claiming_it(timed, monkeypatch):
    from models.parking_slot import ParkingSlot
    context, body, slot, rate = timed
    _client, _current, users, _site, kind, db = context
    order = purchase(timed)
    ticket = db.get(TimedParkingPass, order['timed_pass_id'])
    extra = ParkingSlot(slot_name='T-2', zone_id=slot.zone_id, vehicle_type_id=kind.id, is_active=True, is_occupied=False)
    db.add(extra)
    # Physical zone capacity in the fixture is one; enlarge it explicitly.
    from models.zone import Zone
    db.get(Zone, slot.zone_id).capacity = 2
    db.commit()
    monkeypatch.setattr('crud.parking_session.server_now', lambda: ticket.start_at)
    vehicle = db.get(Vehicle, body['vehicle_id'])
    with pytest.raises(HTTPException) as error:
        ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=extra.id)
    assert error.value.status_code == 409
    db.refresh(extra)
    assert extra.is_occupied is False
    assert db.scalar(select(func.count()).select_from(ParkingSession)) == 0


@pytest.mark.parametrize('extra', [{'amount': 1}, {'end_at': '2026-09-17T12:00:00+07:00'}, {'rate_unit_price': 1}, {'duration_minutes': 600}])
def test_customer_cannot_override_server_owned_terms(timed, extra):
    context, body, *_ = timed
    result = context[0].post('/api/v2/me/orders', json={**body, **extra})
    assert result.status_code == 422
