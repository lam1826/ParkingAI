"""A consumed one-entry reservation releases capacity on actual departure."""
from datetime import timedelta

from sqlalchemy import select

from core.clock import BUSINESS_TZ
from expansion.site_models import ParkingReservation
from expansion.site_service import availability
from models.vehicle import Vehicle
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from test_portal_api import portal  # noqa: F401
from test_timed_parking import timed, purchase  # noqa: F401
from test_timed_parking_acceptance import arrive


def test_early_departure_releases_slot_for_new_purchase_and_walkin(timed, monkeypatch):
    context, body, slot, _rate = timed
    client, _current, users, site, kind, db = context
    order = purchase(timed)
    session, ticket = arrive(timed, order, monkeypatch)
    at = ticket.start_at + timedelta(minutes=1)
    monkeypatch.setattr("crud.parking_session.server_now", lambda: at)
    monkeypatch.setattr("expansion.timed_parking_service.business_now", lambda: at)
    assert availability(db, site.id)["available_now"] == 0
    checkout = CheckoutService(db)
    quote = checkout.quote(session.id, users[0].id)
    checkout.confirm(CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True,
        payment_method=None), users[0].id, session_id=session.id)
    reservation = db.scalar(select(ParkingReservation).where(ParkingReservation.session_id == session.id))
    assert reservation.status == "arrived"  # historical evidence is unchanged
    assert reservation.end_at > at
    assert availability(db, site.id)["available_now"] == 1
    from crud.parking_slot import zone_has_future_commitment
    assert zone_has_future_commitment(db, slot.zone_id) is False
    new_order = client.post("/api/v2/me/orders", json={**body, "idempotency_key": "after-early-exit",
        "start_at": (at + timedelta(minutes=1)).replace(tzinfo=BUSINESS_TZ).isoformat()})
    assert new_order.status_code == 200, new_order.text
    assert client.post(f"/api/v2/me/orders/{new_order.json()['id']}/cancel").status_code == 200
    walkin = Vehicle(license_plate="30A-99992", vehicle_type_id=kind.id)
    db.add(walkin)
    db.commit()
    result = ParkingService(db).check_in(walkin.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    assert result["session_id"] != session.id
    assert availability(db, site.id)["available_now"] == 0


def test_active_overstay_still_blocks_slot_after_reserved_end(timed, monkeypatch):
    context, _body, _slot, _rate = timed
    _client, _current, _users, site, _kind, db = context
    session, ticket = arrive(timed, purchase(timed), monkeypatch)
    at = ticket.end_at + timedelta(hours=1)
    monkeypatch.setattr("crud.parking_session.server_now", lambda: at)
    assert session.status == "active"
    result = availability(db, site.id)
    assert result["occupied"] == 1 and result["available_now"] == 0
