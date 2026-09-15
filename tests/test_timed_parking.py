"""Paid capacity and one-use admission run through the real portal and ledger."""
from datetime import timedelta

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError

from test_portal_api import portal, onboard
from core.clock import BUSINESS_TZ, business_now
from core.billing import snapshot_basis
from expansion.portal_models import PortalOrder
from expansion.timed_parking_models import ParkingCapacityHold, TimedParkingPass
from models.zone import Zone
from models.parking_slot import ParkingSlot
from models.price_config import PriceConfig
from models.parking_session import ParkingSession
from models.payment import Payment


@pytest.fixture
def timed(portal):
    body = onboard(portal)
    client, current, users, site, kind, db = portal
    zone = Zone(name="Timed zone", capacity=1, is_active=True, site_id=site.id)
    db.add(zone)
    db.flush()
    slot = ParkingSlot(slot_name="T-1", zone_id=zone.id, vehicle_type_id=kind.id, is_active=True, is_occupied=False)
    rate = PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=5000,
        effective_date=business_now().date(), is_active=True)
    db.add_all([slot, rate])
    site.customer_booking_mode = "paid_packages"
    db.commit()
    current["user"] = users[0]
    response = client.post("/api/v2/portal/admin/plans", json=dict(name="2 giờ", site_id=site.id,
        vehicle_type_id=kind.id, product_kind="hourly", duration_minutes=120, price=12000))
    assert response.status_code == 200, response.text
    body.update(plan_id=response.json()["id"], start_at=(business_now()+timedelta(minutes=2)).replace(tzinfo=BUSINESS_TZ).isoformat())
    current["user"] = users[1]
    return portal, body, slot, rate


def purchase(timed):
    portal, body, slot, rate = timed
    client = portal[0]
    response = client.post("/api/v2/me/orders", json=body)
    assert response.status_code == 200, response.text
    order = response.json()
    paid = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json=dict(token=order["demo_token"], outcome="success"))
    assert paid.status_code == 200, paid.text
    return paid.json()


def test_timed_purchase_replays_once_and_preserves_price(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    order = purchase(timed)
    assert order["status"] == "fulfilled"
    assert order["entitlement_status"] == "ready"
    assert order["slot"]["id"] == slot.id
    assert order["overstay_basis"]["unit_price"] == 5000
    again = client.post("/api/v2/me/orders", json=body)
    assert again.status_code == 200 and again.json()["id"] == order["id"]
    assert db.scalar(select(func.count()).select_from(TimedParkingPass)) == 1
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.source_type == "portal_order")) == 1
    assert db.scalar(select(ParkingCapacityHold)).status == "converted"
    assert client.get("/api/v2/me/timed-passes").json()["items"][0]["order_id"] == order["id"]
    assert client.get("/api/v2/me/receipts").json()["items"][0]["source_type"] == "portal_order"


def test_timed_admission_snapshots_overstay_and_only_consumes_once(timed, monkeypatch):
    from services.parking_service import ParkingService
    from models.vehicle import Vehicle
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    order = purchase(timed)
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    start, end = ticket.start_at, ticket.end_at
    monkeypatch.setattr("crud.parking_session.server_now", lambda: start)
    vehicle = db.get(Vehicle, body["vehicle_id"])
    result = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    session = db.get(ParkingSession, result["session_id"])
    assert session.timed_pass_id == ticket.id
    assert session.monthly_pass_id is None
    assert ticket.status == "consumed"
    assert snapshot_basis(session, end)["billable_blocks"] == 0
    assert snapshot_basis(session, end+timedelta(microseconds=1))["billable_blocks"] == 1
    assert snapshot_basis(session, end+timedelta(hours=1, microseconds=1))["billable_blocks"] == 2
    assert snapshot_basis(session, end)["rate_source"] == "prepaid_snapshot"
    with pytest.raises(Exception):
        ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)


def test_hold_releases_on_cancel_and_order_snapshot_is_immutable(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    order = client.post("/api/v2/me/orders", json=body).json()
    with pytest.raises(IntegrityError, match="snapshot immutable"):
        db.execute(text("UPDATE portal_orders SET amount=1 WHERE id=:id"), {"id": order["id"]})
    db.rollback()
    result = client.post(f"/api/v2/me/orders/{order['id']}/cancel")
    assert result.status_code == 200, result.text
    assert db.scalar(select(ParkingCapacityHold)).status == "released"
    assert client.post("/api/v2/me/orders", json={**body, "idempotency_key": "next-purchase"}).status_code == 200


def test_customer_cannot_read_other_timed_entitlement_or_receipt(timed):
    portal, *_ = timed
    client, current, users, *_ = portal
    order = purchase(timed)
    current["user"] = users[2]
    assert client.post("/api/v2/me/profile", json={"full_name": "Other", "phone_number": "0902222333"}).status_code == 200
    assert client.get(f"/api/v2/me/orders/{order['id']}").status_code == 404
    assert client.get("/api/v2/me/timed-passes").json()["items"] == []
    assert client.get(f"/api/v2/me/receipts/{order['receipt_id']}/pdf").status_code == 404


def test_expiry_rejects_payment_without_reclaiming_capacity(timed, monkeypatch):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    result = client.post("/api/v2/me/orders", json=body)
    assert result.status_code == 200, result.text
    order = result.json()
    deadline = db.get(PortalOrder, order["id"]).expires_at
    monkeypatch.setattr("expansion.portal_service.business_now", lambda: deadline)
    monkeypatch.setattr("expansion.timed_parking_service.business_now", lambda: deadline)
    paid = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json=dict(token=order["demo_token"], outcome="success"))
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "review"
    assert db.scalar(select(func.count()).select_from(TimedParkingPass)) == 0
    assert db.scalar(select(ParkingCapacityHold)).status == "expired"


def test_reserved_arrival_precedes_nonoverlapping_future_payment_hold(timed, monkeypatch):
    from services.parking_service import ParkingService
    from models.vehicle import Vehicle
    from expansion.portal_models import PortalVehicleOwnership
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    order = purchase(timed)
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    vehicle = db.get(Vehicle, body["vehicle_id"])
    later_vehicle = Vehicle(license_plate="30A-55555", vehicle_type_id=kind.id, customer_id=vehicle.customer_id)
    db.add(later_vehicle)
    db.flush()
    db.add(PortalVehicleOwnership(customer_id=vehicle.customer_id, vehicle_id=later_vehicle.id, approved_by_id=users[0].id))
    db.commit()
    later = client.post("/api/v2/me/orders", json={**body, "vehicle_id": later_vehicle.id,
        "idempotency_key": "future-hold", "start_at": (ticket.end_at+timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ).isoformat()})
    assert later.status_code == 200, later.text
    monkeypatch.setattr("crud.parking_session.server_now", lambda: ticket.start_at)
    result = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    assert db.get(ParkingSession, result["session_id"]).timed_pass_id == ticket.id


def test_paid_mode_blocks_free_reservation_and_hold_blocks_walkin_and_inventory_disable(timed):
    from expansion.reservations import reserve
    from expansion.site_schemas import ReservationCreate
    from fastapi import HTTPException
    from services.parking_service import ParkingService
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    start = business_now()+timedelta(minutes=2)
    request = ReservationCreate(site_id=site.id, vehicle_id=body["vehicle_id"], slot_id=slot.id,
        start_at=start.replace(tzinfo=BUSINESS_TZ), end_at=(start+timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id="free-request-0001")
    with pytest.raises(HTTPException) as err:
        reserve(db, users[1], request, customer=True)
    assert err.value.status_code == 409
    db.rollback()
    assert client.post("/api/v2/me/orders", json=body).status_code == 200
    with pytest.raises(HTTPException) as err:
        ParkingService(db).check_in("30A-66666", kind.id, users[0].id, parking_slot_id=slot.id)
    assert err.value.status_code == 409
    for table, identity in [("parking_slots",slot.id),("zones",slot.zone_id),("vehicle_types",kind.id)]:
        with pytest.raises(IntegrityError, match="payment holds"):
            db.execute(text(f"UPDATE {table} SET is_active=0 WHERE id=:id"),{"id":identity})
        db.rollback()


def test_paid_unused_refund_revokes_capacity_and_preserves_receipt(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    order = purchase(timed)
    response = client.post(f"/api/v2/me/orders/{order['id']}/refund-requests", json={"reason":"Không còn nhu cầu"})
    assert response.status_code == 200, response.text
    current["user"] = users[0]
    result = client.post(f"/api/v2/portal/admin/refund-requests/{response.json()['id']}/resolve", json={"approve":True,"note":"Đã kiểm tra"})
    assert result.status_code == 200, result.text
    assert db.get(TimedParkingPass, order["timed_pass_id"]).status == "revoked"
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.source_type=="portal_order")) == 2
