"""Review 05/10/2026 #1 (P1-2), #26, #27, #81, #45: direct manager refunds vs entitlements.

A direct refund (Site Finance "Hoàn tiền" or legacy POST /api/v1/payments/{id}/refund)
only writes a ledger row. It must not refund a portal entitlement (prepaid
ticket or portal monthly period) or a receipt with an open customer request:
those go through the receipt-based request workflow (DECISIONS 2026-09-16).
A counter monthly period that becomes fully refunded is stopped, and a
refunded period cannot be switched back on.
"""
from datetime import timedelta

from sqlalchemy import func, select

from core.clock import BUSINESS_TZ, business_now
from expansion.portal_models import PortalOrder
from expansion.site_finance import router as finance_router
from expansion.site_models import ParkingReservation
from expansion.support_router import router as support_router
from expansion.timed_parking_models import TimedParkingPass
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.vehicle import Vehicle
from routers.monthly_pass import router as monthly_router
from routers.payment import router as payment_router
from schemas.monthly_pass import MonthlyPassCreate
from services.monthly_subscription_service import create_subscription
from test_online_payments import no_external_payment_configuration, online  # noqa: F401
from test_portal_api import onboard, portal  # noqa: F401
from test_refund_requests import _collected_manual_order
from test_timed_parking import timed  # noqa: F401


def _routes(client):
    # The portal fixture builds a fresh application per test.
    client.app.include_router(finance_router, prefix="/api/v2")
    client.app.include_router(support_router, prefix="/api/v2")
    client.app.include_router(payment_router, prefix="/api/v1/payments")
    client.app.include_router(monthly_router, prefix="/api/v1/monthly-passes")


def _refund_body(amount, key):
    return {"amount": amount, "method": "cash", "reason": "Hoàn tại quầy", "idempotency_key": key}


def _refunds(db, receipt_id):
    return sum(db.scalars(select(Payment.amount).where(Payment.original_payment_id == receipt_id, Payment.kind == "refund")))


def _site_row(client, site, receipt_id):
    return next(row for row in client.get(f"/api/v2/sites/{site.id}/payments").json()["items"] if row["id"] == receipt_id)


def _manual_timed_order(timed, key):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    start = (business_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    body.update(payment_mode="manual", idempotency_key=key, start_at=start.replace(tzinfo=BUSINESS_TZ).isoformat())
    made = client.post("/api/v2/me/orders", json=body)
    assert made.status_code == 200, made.text
    current["user"] = users[0]
    collected = client.post(f"/api/v2/portal/admin/orders/{made.json()['id']}/collect", json={"payment_method": "cash", "confirmed": True})
    assert collected.status_code == 200, collected.text
    return collected.json()


def _counter_pass(db, users, start=None, days=29, price=300000, code="COUNTER-0001"):
    customer = db.scalar(select(Customer).where(Customer.full_name == "Khách A"))
    vehicle = db.scalar(select(Vehicle).where(Vehicle.customer_id == customer.id))
    start = start or business_now().date() + timedelta(days=40)
    period = create_subscription(db, MonthlyPassCreate(customer_id=customer.id, vehicle_id=vehicle.id, pass_code=code,
        price=price, start_date=start, end_date=start + timedelta(days=days), payment_method="cash"), users[0].id)
    receipt = db.scalar(select(Payment).where(Payment.source_type == "monthly_pass", Payment.source_id == str(period.id)))
    return period, receipt


def test_direct_refund_of_prepaid_ticket_is_refused_on_both_endpoints(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _manual_timed_order(timed, "direct-timed-0001")
    site_refund = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(12000, "direct-site-0001"))
    assert site_refund.status_code == 409 and "yêu cầu hoàn" in site_refund.json()["detail"]
    legacy = client.post(f"/api/v1/payments/{order['receipt_id']}/refund", json=_refund_body(12000, "direct-legacy-0001"))
    assert legacy.status_code == 409, legacy.text
    row = _site_row(client, site, order["receipt_id"])
    assert row["direct_refund_blocked_reason"] == "portal_ticket" and row["direct_refund_blocked_label"]
    db.expire_all()
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    assert ticket.status == "ready" and db.get(PortalOrder, order["id"]).status == "fulfilled"
    assert db.get(ParkingReservation, ticket.reservation_id).status == "confirmed"
    assert _refunds(db, order["receipt_id"]) == 0
    # The customer's request workflow (which revokes the ticket) stays open.
    current["user"] = users[1]
    mine = next(r for r in client.get("/api/v2/me/receipts").json()["items"] if r["id"] == order["receipt_id"])
    assert mine["refund"]["eligible"] is True


def test_direct_refund_of_portal_monthly_period_is_refused(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="direct-monthly-0001")
    current["user"] = users[0]
    refused = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(300000, "direct-site-0002"))
    assert refused.status_code == 409, refused.text
    assert _site_row(client, site, order["receipt_id"])["direct_refund_blocked_reason"] == "portal_monthly"
    legacy = client.post(f"/api/v1/payments/{order['receipt_id']}/refund", json=_refund_body(300000, "direct-legacy-0002"))
    assert legacy.status_code == 409, legacy.text
    db.expire_all()
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is True
    assert db.get(PortalOrder, order["id"]).status == "fulfilled" and _refunds(db, order["receipt_id"]) == 0


def test_a_portal_period_stopped_by_the_manager_can_still_be_refunded_directly(portal):
    """Rework of #26: "Ngừng vé" tells the manager to refund in Thu tiền & Chốt ca.

    A stopped portal period has no entitlement left to revoke and the customer
    can no longer request (pass_inactive), so the direct refund is the only way
    to return the money. A full refund settles the portal order like the
    request workflow and the period stays off.
    """
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="direct-monthly-stopped-0001")
    current["user"] = users[0]
    stopped = client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": False})
    assert stopped.status_code == 200, stopped.text
    assert _site_row(client, site, order["receipt_id"])["direct_refund_blocked_reason"] is None
    partial = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(100000, "direct-stopped-0001"))
    assert partial.status_code == 200, partial.text
    db.expire_all()
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"
    rest = client.post(f"/api/v1/payments/{order['receipt_id']}/refund", json=_refund_body(order["amount"] - 100000, "direct-stopped-0002"))
    assert rest.status_code == 200, rest.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == order["amount"]
    assert db.get(PortalOrder, order["id"]).status == "refunded"
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is False
    # Refunded money cannot be turned back into an active period (#81).
    again = client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": True})
    assert again.status_code == 409, again.text
    current["user"] = users[1]
    mine = next(row for row in client.get("/api/v2/me/receipts").json()["items"] if row["id"] == order["receipt_id"])
    assert mine["refund"]["blocked_reason"] == "fully_refunded"


def test_a_stopped_portal_period_with_an_open_request_stays_in_the_workflow(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="direct-monthly-stopped-0002")
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Không dùng"})
    assert request.status_code == 201, request.text
    current["user"] = users[0]
    assert client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": False}).status_code == 200
    refused = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(100000, "direct-stopped-0003"))
    assert refused.status_code == 409, refused.text
    assert _site_row(client, site, order["receipt_id"])["direct_refund_blocked_reason"] == "request_open"
    assert _refunds(db, order["receipt_id"]) == 0


def test_full_direct_refund_of_counter_period_stops_it_partial_keeps_it(portal):
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    period, receipt = _counter_pass(db, users)
    assert receipt.site_id == site.id
    current["user"] = users[0]
    assert _site_row(client, site, receipt.id)["direct_refund_blocked_reason"] is None
    partial = client.post(f"/api/v2/sites/{site.id}/payments/{receipt.id}/refund", json=_refund_body(100000, "direct-site-0003"))
    assert partial.status_code == 200, partial.text
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is True
    rest = client.post(f"/api/v1/payments/{receipt.id}/refund", json=_refund_body(200000, "direct-legacy-0003"))
    assert rest.status_code == 200, rest.text
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is False and _refunds(db, receipt.id) == 300000
    # #81: a refunded period cannot be switched back on.
    again = client.put(f"/api/v1/monthly-passes/{period.id}", json={"is_active": True})
    assert again.status_code == 409, again.text
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is False


def test_full_direct_refund_waits_while_the_counter_period_covers_a_parked_car(timed, monkeypatch):
    from services.parking_service import ParkingService
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    period, receipt = _counter_pass(db, users, start=business_now().date(), code="COUNTER-PARKED")
    vehicle = db.get(Vehicle, period.vehicle_id)
    admitted = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    assert admitted["session_id"]
    current["user"] = users[0]
    refused = client.post(f"/api/v2/sites/{site.id}/payments/{receipt.id}/refund", json=_refund_body(300000, "direct-site-0004"))
    assert refused.status_code == 409 and "trong bãi" in refused.json()["detail"]
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is True and _refunds(db, receipt.id) == 0


def test_direct_refund_never_bypasses_an_open_request(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="direct-open-request-0001")
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Chuyển công tác"})
    assert request.status_code == 201, request.text
    request = request.json()
    current["user"] = users[0]
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    assert client.post(url + "/approve", json={"amount": 100000}).status_code == 200
    for key, amount in (("direct-site-0005", 100000), ("direct-site-0006", 300000)):
        refused = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(amount, key))
        assert refused.status_code == 409, refused.text
    assert client.post(f"/api/v1/payments/{order['receipt_id']}/refund", json=_refund_body(100000, "direct-legacy-0005")).status_code == 409
    row = _site_row(client, site, order["receipt_id"])
    assert row["direct_refund_blocked_reason"] == "request_open" and row["open_refund_request_id"] == request["id"]
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["status"] == "refunded" and _refunds(db, order["receipt_id"]) == 100000


def test_counter_receipt_with_an_open_request_is_not_refunded_directly(portal):
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    period, receipt = _counter_pass(db, users)
    assert client.post(f"/api/v2/me/receipts/{receipt.id}/refund-requests", json={"reason": "Đổi ý"}).status_code == 201
    current["user"] = users[0]
    assert _site_row(client, site, receipt.id)["direct_refund_blocked_reason"] == "request_open"
    refused = client.post(f"/api/v2/sites/{site.id}/payments/{receipt.id}/refund", json=_refund_body(100000, "direct-site-0007"))
    assert refused.status_code == 409 and _refunds(db, receipt.id) == 0


def test_reactivating_a_stopped_but_unrefunded_period_still_works(portal):
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    period, receipt = _counter_pass(db, users)
    current["user"] = users[0]
    assert client.put(f"/api/v1/monthly-passes/{period.id}", json={"is_active": False}).status_code == 200
    restored = client.put(f"/api/v1/monthly-passes/{period.id}", json={"is_active": True})
    assert restored.status_code == 200, restored.text
    assert restored.json()["is_active"] is True


def test_refunded_portal_period_cannot_be_reactivated(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    paid = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"}).json()
    request = client.post(f"/api/v2/me/receipts/{paid['receipt_id']}/refund-requests", json={"reason": "Không dùng"}).json()
    current["user"] = users[0]
    assert client.post(f"/api/v2/sites/{site.id}/refund-requests/{request['id']}/approve", json={}).json()["status"] == "refunded"
    response = client.put(f"/api/v1/monthly-passes/{paid['monthly_pass_id']}", json={"is_active": True})
    assert response.status_code == 409, response.text
    db.expire_all()
    assert db.get(MonthlyPass, paid["monthly_pass_id"]).is_active is False


def test_legacy_payment_list_and_detail_accept_every_ledger_source(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _manual_timed_order(timed, "legacy-list-0001")
    listed = client.get("/api/v1/payments")
    assert listed.status_code == 200, listed.text
    assert {row["source_type"] for row in listed.json()["items"]} >= {"portal_order"}
    filtered = client.get("/api/v1/payments", params={"source_type": "portal_order"})
    assert filtered.status_code == 200 and filtered.json()["total"] == 1
    detail = client.get(f"/api/v1/payments/{order['receipt_id']}")
    assert detail.status_code == 200 and detail.json()["source_type"] == "portal_order"
    assert db.scalar(select(func.count()).select_from(Payment)) == 1
