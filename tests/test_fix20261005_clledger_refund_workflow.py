"""Review 05/10/2026 #6, #23, #50, #76, #80: the receipt refund workflow.

#6  A receipt without a site cannot open a request nobody can see; a historical
    site-less request is reachable by a global admin from a site queue.
#23 A counter/online approval of a prepaid hour/day ticket revokes the ticket at
    the decision, so the approved refund stays recordable after the window starts.
#50 A 0 ₫ balancing receipt is "nothing collected", never "already refunded".
#76 A request on a receipt of an inactive site is refused (its queue cannot open).
#80 A manager stopping the monthly period after (or before) the decision does not
    strand the approved refund.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select

import core.clock as clock
from core.clock import BUSINESS_TZ, business_now
from expansion.portal_models import PortalOrder
from expansion.site_models import ParkingReservation, SiteMembership
from expansion.support_models import PaymentRefundRequest
from expansion.support_router import router as support_router
from expansion.timed_parking_models import TimedParkingPass
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from routers.monthly_pass import router as monthly_router
from schemas.monthly_pass import MonthlyPassCreate
from services.monthly_subscription_service import create_subscription
from services.payment_service import PaymentService
from test_portal_api import onboard, portal  # noqa: F401
from test_refund_requests import _collected_manual_order
from test_timed_parking import timed  # noqa: F401


def _routes(client):
    client.app.include_router(support_router, prefix="/api/v2")
    client.app.include_router(monthly_router, prefix="/api/v1/monthly-passes")


def _freeze(monkeypatch, instant):
    instant = instant.replace(tzinfo=BUSINESS_TZ)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Frozen)


def _customer_vehicle(db):
    customer = db.scalar(select(Customer).where(Customer.full_name == "Khách A"))
    return customer, db.scalar(select(Vehicle).where(Vehicle.customer_id == customer.id))


def _counter_pass(db, users, *, price=300000, code="LEDGER-0001"):
    customer, vehicle = _customer_vehicle(db)
    start = business_now().date() + timedelta(days=40)
    period = create_subscription(db, MonthlyPassCreate(customer_id=customer.id, vehicle_id=vehicle.id, pass_code=code,
        price=price, start_date=start, end_date=start + timedelta(days=29), payment_method="cash"), users[0].id)
    receipt = db.scalar(select(Payment).where(Payment.source_type == "monthly_pass", Payment.source_id == str(period.id)))
    return period, receipt


def _receipt_row(client, receipt_id):
    return next(row for row in client.get("/api/v2/me/receipts").json()["items"] if row["id"] == receipt_id)


def _site_manager(db, site):
    role = db.scalar(select(Role).where(Role.name == "manager"))
    if role is None:
        role = Role(name="manager")
        db.add(role)
        db.flush()
    manager = User(username="ledger_manager", full_name="Manager", password_hash="unused", role_id=role.id, is_active=True)
    db.add(manager)
    db.flush()
    db.add(SiteMembership(site_id=site.id, user_id=manager.id, role="manager"))
    db.commit()
    return manager


def test_site_less_receipt_is_not_requestable_and_orphans_reach_the_global_admin(portal):
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    customer, vehicle = _customer_vehicle(db)
    start = business_now().date() + timedelta(days=40)
    period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=200000, start_date=start,
        end_date=start + timedelta(days=29), pass_code="HISTORICAL-0001")
    db.add(period)
    db.flush()
    # A historical counter receipt recorded before receipts carried a site.
    receipt = PaymentService.record_receipt(db, "monthly_pass", period.id, 200000, None, "cash")
    db.commit()
    assert receipt.site_id is None
    state = _receipt_row(client, receipt.id)["refund"]
    assert state["eligible"] is False and state["blocked_reason"] == "site_unknown" and state["blocked_label"]
    refused = client.post(f"/api/v2/me/receipts/{receipt.id}/refund-requests", json={"reason": "Không dùng"})
    assert refused.status_code == 409, refused.text
    assert db.scalar(select(func.count()).select_from(PaymentRefundRequest)) == 0
    # A request filed by the earlier code (site_id NULL) is no longer orphaned.
    now = business_now()
    orphan = PaymentRefundRequest(receipt_id=receipt.id, site_id=None, customer_id=customer.id, user_id=users[1].id,
        source_type="monthly_pass", source_id=receipt.source_id, payment_channel="counter", receipt_method="cash",
        reason="Yêu cầu cũ", requested_amount=200000, created_at=now, updated_at=now)
    db.add(orphan)
    db.commit()
    manager = _site_manager(db, site)
    current["user"] = manager
    assert orphan.id not in [row["id"] for row in client.get(f"/api/v2/sites/{site.id}/refund-requests").json()["items"]]
    assert client.post(f"/api/v2/sites/{site.id}/refund-requests/{orphan.id}/approve", json={}).status_code == 404
    current["user"] = users[0]
    assert orphan.id in [row["id"] for row in client.get(f"/api/v2/sites/{site.id}/refund-requests").json()["items"]]
    url = f"/api/v2/sites/{site.id}/refund-requests/{orphan.id}"
    assert client.get(url).json()["refund_state"]["eligible"] is True
    approved = client.post(url + "/approve", json={})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is False


def _approved_ticket_refund(timed, key):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    start = (business_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    body.update(payment_mode="manual", idempotency_key=key, start_at=start.replace(tzinfo=BUSINESS_TZ).isoformat())
    order = client.post("/api/v2/me/orders", json=body)
    assert order.status_code == 200, order.text
    current["user"] = users[0]
    collected = client.post(f"/api/v2/portal/admin/orders/{order.json()['id']}/collect", json={"payment_method": "cash", "confirmed": True})
    assert collected.status_code == 200, collected.text
    order = collected.json()
    current["user"] = users[1]
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Đổi lịch"})
    assert request.status_code == 201, request.text
    current["user"] = users[0]
    url = f"/api/v2/sites/{site.id}/refund-requests/{request.json()['id']}"
    approved = client.post(url + "/approve", json={"note": "Duyệt tối nay"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    return order, request.json(), url


def test_approval_revokes_the_ticket_and_the_refund_stays_recordable_after_start(timed, monkeypatch):
    portal = timed[0]
    client, current, users, site, kind, db = portal
    order, request, url = _approved_ticket_refund(timed, "ledger-timed-0001")
    db.expire_all()
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    assert ticket.status == "revoked"
    assert db.get(ParkingReservation, ticket.reservation_id).status == "cancelled"
    detail = client.get(url).json()
    assert detail["entitlement_revoked"] is True and detail["refund_state"]["eligible"] is True
    # Rejecting would leave the customer with neither ticket nor money.
    rejected = client.post(url + "/reject", json={"note": "Không hoàn"})
    assert rejected.status_code == 409, rejected.text
    # The manager pays out the next morning, after the ticket window started.
    _freeze(monkeypatch, ticket.start_at + timedelta(hours=1))
    recorded = client.post(url + "/record-refund", json={"method": "transfer", "external_reference": "FT26100500999", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    db.expire_all()
    assert db.get(PortalOrder, order["id"]).status == "refunded"
    refunds = db.scalars(select(Payment).where(Payment.kind == "refund")).all()
    assert [row.amount for row in refunds] == [order["amount"]]


def test_a_ticket_revoked_at_approval_cannot_admit_the_car(timed, monkeypatch):
    from services.parking_service import ParkingService
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    order, request, url = _approved_ticket_refund(timed, "ledger-timed-0002")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    _freeze(monkeypatch, ticket.start_at + timedelta(minutes=1))
    vehicle = db.get(Vehicle, ticket.vehicle_id)
    try:
        admitted = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    except Exception:  # noqa: BLE001 - any refusal keeps the revoked ticket unused
        db.rollback()
        admitted = None
    db.expire_all()
    assert db.get(TimedParkingPass, ticket.id).status == "revoked"
    if admitted is not None:
        from models.parking_session import ParkingSession
        assert db.get(ParkingSession, admitted["session_id"]).timed_pass_id is None
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text


def test_zero_receipt_is_nothing_collected_not_fully_refunded(portal):
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    period, receipt = _counter_pass(db, users, price=0, code="ZERO-0001")
    db.commit()
    assert receipt.amount == 0
    state = _receipt_row(client, receipt.id)["refund"]
    assert state["blocked_reason"] == "nothing_collected"
    assert "hoàn hết" not in state["blocked_label"] and "0 ₫" in state["blocked_label"]


def test_request_on_an_inactive_site_receipt_is_refused(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="ledger-inactive-0001")
    site.is_active = False
    db.commit()
    state = _receipt_row(client, order["receipt_id"])["refund"]
    assert state["blocked_reason"] == "site_inactive"
    refused = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Bãi đóng"})
    assert refused.status_code == 409, refused.text
    assert db.scalar(select(func.count()).select_from(PaymentRefundRequest)) == 0


def _requested_monthly_refund(portal, key):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key=key)
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Chuyển nhà"})
    assert request.status_code == 201, request.text
    current["user"] = users[0]
    return order, f"/api/v2/sites/{site.id}/refund-requests/{request.json()['id']}"


def test_stopping_the_pass_after_approval_still_lets_the_refund_be_recorded(portal):
    client, current, users, site, kind, db = portal
    order, url = _requested_monthly_refund(portal, "ledger-stop-after-0001")
    assert client.post(url + "/approve", json={}).json()["status"] == "approved"
    stopped = client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": False})
    assert stopped.status_code == 200, stopped.text
    assert client.get(url).json()["refund_state"]["eligible"] is True
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    assert sum(db.scalars(select(Payment.amount).where(Payment.kind == "refund"))) == order["amount"]
    db.expire_all()
    assert db.get(PortalOrder, order["id"]).status == "refunded"


def test_stopping_the_pass_before_approval_does_not_block_the_decision(portal):
    client, current, users, site, kind, db = portal
    order, url = _requested_monthly_refund(portal, "ledger-stop-before-0001")
    assert client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": False}).status_code == 200
    approved = client.post(url + "/approve", json={})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    assert client.post(url + "/record-refund", json={"method": "cash", "confirmed": True}).json()["status"] == "refunded"


def test_a_pass_stopped_without_a_decision_still_blocks_new_requests(portal):
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    period, receipt = _counter_pass(db, users, code="STOP-NEW-0001")
    current["user"] = users[0]
    assert client.put(f"/api/v1/monthly-passes/{period.id}", json={"is_active": False}).status_code == 200
    current["user"] = users[1]
    assert _receipt_row(client, receipt.id)["refund"]["blocked_reason"] == "pass_inactive"
