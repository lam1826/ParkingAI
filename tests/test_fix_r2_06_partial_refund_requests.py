"""Review 28/10/2026 R2-06: only a refund that empties the receipt ends the entitlement.

Binding rule R2-06: the settle test is the ledger formula of a direct refund
(refunded so far + amount >= receipt amount), evaluated before the ledger row
is written, for approvals and recordings of every channel. A partial amount is
compensation: the ticket or monthly period stays usable, the portal order
stays fulfilled and the remainder stays requestable under the usual guards.
Recording an approved partial is not blocked by a ticket used or a car parked
under the pass meanwhile. A remainder the earlier rule stranded (portal order
'refunded' with money left) is requestable again. Round 2: money is never
stranded, so the DEMO remainder of a period the manager stopped stays
requestable, while a stopped counter/online period stays with Site Finance.
The checks around the rule: an approved partial can still be rejected,
approval guards while the car is parked, the notification of an old-rule
remainder.
"""
from datetime import timedelta

from sqlalchemy import select

from core.clock import BUSINESS_TZ, business_now
from expansion.portal_models import PortalNotification, PortalOrder
from expansion.site_models import ParkingReservation
from expansion.support_models import PaymentRefundRequest
from expansion.timed_parking_models import TimedParkingPass
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.vehicle import Vehicle
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from services.payment_service import PaymentService
from test_fix20261005_clledger_direct_refund import _counter_pass, _manual_timed_order, _refund_body, _refunds, _routes, _site_row
from test_fix20261005_clledger_refund_workflow import _freeze
from test_portal_api import onboard, portal  # noqa: F401
from test_refund_requests import _collected_manual_order, _paid_demo_order, _receipt_row
from test_timed_parking import purchase, timed  # noqa: F401

PARTIAL_DEMO = ("Đã hoàn mô phỏng DEMO một phần. Vé/kỳ vé vẫn còn hiệu lực; bạn có thể gửi yêu cầu hoàn phần còn lại "
    "nếu muốn dừng vé. Không có tiền thật được chuyển.")
PARTIAL_APPROVED = ("Yêu cầu hoàn tiền được duyệt một phần. Vé/kỳ vé vẫn còn hiệu lực; tiền sẽ được hoàn theo hình thức "
    "quản lý ghi nhận, duyệt chưa có nghĩa tiền đã về tài khoản.")
FULL_DEMO = "Đã hoàn mô phỏng DEMO và dừng quyền sử dụng liên quan; không có tiền thật được chuyển."
APPROVED = ("Yêu cầu hoàn tiền đã được duyệt. Tiền sẽ được hoàn theo hình thức quản lý ghi nhận; "
    "duyệt chưa có nghĩa tiền đã về tài khoản.")
IN_USE = "Kỳ vé đang được dùng cho xe trong bãi; hãy hoàn tất lượt gửi trước."


def _request(client, current, users, receipt_id, reason="Không dùng hết"):
    current["user"] = users[1]
    created = client.post(f"/api/v2/me/receipts/{receipt_id}/refund-requests", json={"reason": reason})
    assert created.status_code == 201, created.text
    current["user"] = users[0]
    return created.json()


def _notice(db, key):
    return db.scalar(select(PortalNotification.message).where(PortalNotification.event_key == key))


def _ticket_order(timed, key):
    portal, body, slot, rate = timed
    start = (business_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    body.update(idempotency_key=key, start_at=start.replace(tzinfo=BUSINESS_TZ).isoformat())
    return purchase(timed)


def _old_partial(db, users, receipt_id, amount, *, method):
    """The state the earlier partial approval left behind, with its closed request."""
    receipt = db.get(Payment, receipt_id)
    refund = PaymentService.refund(db, receipt_id, users[0], amount=amount, method=method,
        reason="Hoàn một phần theo quy tắc cũ", idempotency_key="old-partial-" + receipt_id)
    now = business_now()
    customer = db.scalar(select(Customer).where(Customer.full_name == "Khách A"))
    db.add(PaymentRefundRequest(receipt_id=receipt.id, site_id=receipt.site_id, customer_id=customer.id, user_id=users[1].id,
        source_type=receipt.source_type, source_id=receipt.source_id,
        payment_channel="demo" if method == "demo" else "counter", receipt_method=receipt.method,
        reason="Quy tắc cũ", requested_amount=receipt.amount, approved_amount=amount, status="refunded",
        reviewed_by_id=users[0].id, reviewed_at=now, refund_payment_id=refund.id, refund_method=method,
        refunded_by_id=users[0].id, refunded_at=now, created_at=now, updated_at=now))
    db.flush()


def test_partial_demo_monthly_approval_keeps_the_period_and_the_rest_stays_requestable(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _paid_demo_order(portal)
    request = _request(client, current, users, order["receipt_id"])
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    approved = client.post(url + "/approve", json={"amount": 50000, "note": "Hoàn một phần"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "refunded" and approved.json()["approved_amount"] == 50000
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == 50000
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is True
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"
    assert _notice(db, f"refund:{request['id']}:refunded") == PARTIAL_DEMO
    current["user"] = users[1]
    state = _receipt_row(client, order["receipt_id"])["refund"]
    assert state["eligible"] is True and state["refundable_amount"] == 250000 and state["blocked_reason"] is None
    rest = _request(client, current, users, order["receipt_id"], reason="Dừng hẳn vé tháng")
    assert rest["requested_amount"] == 250000
    full = client.post(f"/api/v2/sites/{site.id}/refund-requests/{rest['id']}/approve", json={})
    assert full.status_code == 200 and full.json()["status"] == "refunded", full.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == 300000
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is False
    assert db.get(PortalOrder, order["id"]).status == "refunded"
    assert _notice(db, f"refund:{rest['id']}:refunded") == FULL_DEMO
    current["user"] = users[1]
    assert _receipt_row(client, order["receipt_id"])["refund"]["blocked_reason"] == "fully_refunded"


def test_partial_demo_ticket_approval_keeps_the_ticket_until_the_rest_is_refunded(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _ticket_order(timed, "partial-demo-ticket-0001")
    request = _request(client, current, users, order["receipt_id"])
    approved = client.post(f"/api/v2/sites/{site.id}/refund-requests/{request['id']}/approve", json={"amount": 4000})
    assert approved.status_code == 200 and approved.json()["status"] == "refunded", approved.text
    db.expire_all()
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    assert ticket.status == "ready" and db.get(ParkingReservation, ticket.reservation_id).status == "confirmed"
    assert db.get(PortalOrder, order["id"]).status == "fulfilled" and _refunds(db, order["receipt_id"]) == 4000
    current["user"] = users[1]
    detail = client.get(f"/api/v2/me/orders/{order['id']}").json()
    assert detail["status"] == "fulfilled" and "request_refund" in detail["allowed_actions"]
    assert detail["entitlement_status"] == "ready"
    assert _receipt_row(client, order["receipt_id"])["refund"]["refundable_amount"] == 8000
    rest = _request(client, current, users, order["receipt_id"], reason="Không đi nữa")
    assert rest["requested_amount"] == 8000
    full = client.post(f"/api/v2/sites/{site.id}/refund-requests/{rest['id']}/approve", json={})
    assert full.status_code == 200 and full.json()["status"] == "refunded", full.text
    db.expire_all()
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    assert ticket.status == "revoked" and db.get(ParkingReservation, ticket.reservation_id).status == "cancelled"
    assert db.get(PortalOrder, order["id"]).status == "refunded" and _refunds(db, order["receipt_id"]) == 12000


def test_partial_counter_ticket_is_recorded_after_the_ticket_was_used(timed, monkeypatch):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _manual_timed_order(timed, "partial-used-ticket-0001")
    request = _request(client, current, users, order["receipt_id"])
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    approved = client.post(url + "/approve", json={"amount": 4000})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    db.expire_all()
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    assert ticket.status == "ready" and client.get(url).json()["entitlement_revoked"] is False
    _freeze(monkeypatch, ticket.start_at + timedelta(minutes=1))
    vehicle = db.get(Vehicle, ticket.vehicle_id)
    admitted = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    assert admitted["session_id"]
    db.expire_all()
    assert db.get(TimedParkingPass, ticket.id).status == "consumed"
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == 4000 and db.get(PortalOrder, order["id"]).status == "fulfilled"
    current["user"] = users[1]
    remainder = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Phần còn lại"})
    assert remainder.status_code == 409 and remainder.json()["detail"] == "Vé đã được sử dụng nên không hoàn."


def test_partial_counter_monthly_is_recorded_while_the_car_is_parked(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    period, receipt = _counter_pass(db, users, start=business_now().date(), code="PARTIAL-PARKED")
    request = _request(client, current, users, receipt.id)
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    approved = client.post(url + "/approve", json={"amount": 100000})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    vehicle = db.get(Vehicle, period.vehicle_id)
    admitted = ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is True and _refunds(db, receipt.id) == 100000
    current["user"] = users[1]
    assert _receipt_row(client, receipt.id)["refund"]["blocked_reason"] == "pass_in_use"
    service = CheckoutService(db)
    quote = service.quote(admitted["session_id"], users[0].id)
    service.confirm(CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True,
        payment_method="cash" if quote["parking_fee"] else None), users[0].id, session_id=admitted["session_id"])
    state = _receipt_row(client, receipt.id)["refund"]
    assert state["eligible"] is True and state["refundable_amount"] == 200000
    assert _request(client, current, users, receipt.id, reason="Phần còn lại")["requested_amount"] == 200000


def test_demo_remainder_stranded_by_the_old_rule_is_requestable_again(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _paid_demo_order(portal)
    _old_partial(db, users, order["receipt_id"], 50000, method="demo")
    db.get(MonthlyPass, order["monthly_pass_id"]).is_active = False
    db.get(PortalOrder, order["id"]).status = "refunded"
    db.commit()
    current["user"] = users[1]
    state = _receipt_row(client, order["receipt_id"])["refund"]
    assert state["eligible"] is True and state["refundable_amount"] == 250000
    created = client.post(f"/api/v2/me/orders/{order['id']}/refund-requests", json={"reason": "Phần còn lại"})
    # The order-addressed endpoint has always answered 200 (portal_router.py); the
    # receipt-addressed one answers 201. No status code changes here.
    assert created.status_code == 200, created.text
    assert created.json()["requested_amount"] == 250000
    current["user"] = users[0]
    approved = client.post(f"/api/v2/sites/{site.id}/refund-requests/{created.json()['id']}/approve", json={})
    assert approved.status_code == 200 and approved.json()["status"] == "refunded", approved.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == 300000
    assert db.get(PortalOrder, order["id"]).status == "refunded"
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is False


def test_counter_ticket_remainder_stranded_by_the_old_rule_is_approved_without_revoking(timed, monkeypatch):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _manual_timed_order(timed, "old-partial-ticket-0001")
    _old_partial(db, users, order["receipt_id"], 4000, method="cash")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    ticket.status = "revoked"
    db.get(ParkingReservation, ticket.reservation_id).status = "cancelled"
    db.get(PortalOrder, order["id"]).status = "refunded"
    db.commit()
    request = _request(client, current, users, order["receipt_id"], reason="Phần còn lại")
    assert request["requested_amount"] == 8000

    def must_not_revoke(*_args, **_kwargs):
        raise AssertionError("an already revoked ticket must not be revoked again")

    monkeypatch.setattr("expansion.timed_parking_service.revoke", must_not_revoke)
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    approved = client.post(url + "/approve", json={})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == 12000 and db.get(PortalOrder, order["id"]).status == "refunded"


def test_partial_approval_keeps_a_portal_period_in_the_customer_workflow(portal):
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="partial-portal-monthly-0001")
    request = _request(client, current, users, order["receipt_id"])
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    assert client.post(url + "/approve", json={"amount": 100000}).json()["status"] == "approved"
    recorded = client.post(url + "/record-refund", json={"method": "cash", "confirmed": True})
    assert recorded.status_code == 200 and recorded.json()["status"] == "refunded", recorded.text
    db.expire_all()
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is True
    assert db.get(PortalOrder, order["id"]).status == "fulfilled"
    assert _site_row(client, site, order["receipt_id"])["direct_refund_blocked_reason"] == "portal_monthly"
    current["user"] = users[1]
    assert _receipt_row(client, order["receipt_id"])["refund"]["refundable_amount"] == 200000


def test_a_demo_remainder_stays_requestable_after_the_manager_stops_the_period(portal):
    """Round 2 (root decision): money is never stranded. A DEMO receipt is refunded only through
    the request workflow (Site Finance refuses it, #81 keeps a period with a refund off), so after
    the manager stops a partially refunded DEMO period its remainder stays requestable."""
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _paid_demo_order(portal)
    request = _request(client, current, users, order["receipt_id"])
    approved = client.post(f"/api/v2/sites/{site.id}/refund-requests/{request['id']}/approve", json={"amount": 50000})
    assert approved.status_code == 200 and approved.json()["status"] == "refunded", approved.text
    stopped = client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": False})
    assert stopped.status_code == 200, stopped.text
    direct = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(250000, "demo-stopped-0001"))
    assert direct.status_code == 409, direct.text
    assert client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": True}).status_code == 409
    current["user"] = users[1]
    state = _receipt_row(client, order["receipt_id"])["refund"]
    assert state["eligible"] is True and state["refundable_amount"] == 250000 and state["blocked_reason"] is None
    rest = _request(client, current, users, order["receipt_id"], reason="Kỳ vé đã bị ngừng")
    assert rest["requested_amount"] == 250000
    full = client.post(f"/api/v2/sites/{site.id}/refund-requests/{rest['id']}/approve", json={})
    assert full.status_code == 200 and full.json()["status"] == "refunded", full.text
    db.expire_all()
    assert _refunds(db, order["receipt_id"]) == 300000
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is False
    assert db.get(PortalOrder, order["id"]).status == "refunded"
    current["user"] = users[1]
    assert _receipt_row(client, order["receipt_id"])["refund"]["blocked_reason"] == "fully_refunded"


def test_a_stopped_period_paid_at_the_counter_keeps_its_remainder_in_site_finance(portal):
    """Control for the DEMO relief: a non-DEMO portal period stopped after a partial refund stays
    out of the customer workflow (pass_inactive); Site Finance refunds the remainder directly."""
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _collected_manual_order(portal, key="stopped-manual-partial-01")
    request = _request(client, current, users, order["receipt_id"])
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    assert client.post(url + "/approve", json={"amount": 100000}).json()["status"] == "approved"
    assert client.post(url + "/record-refund", json={"method": "cash", "confirmed": True}).status_code == 200
    assert client.put(f"/api/v1/monthly-passes/{order['monthly_pass_id']}", json={"is_active": False}).status_code == 200
    current["user"] = users[1]
    state = _receipt_row(client, order["receipt_id"])["refund"]
    assert state["eligible"] is False and state["blocked_reason"] == "pass_inactive"
    current["user"] = users[0]
    assert _site_row(client, site, order["receipt_id"])["direct_refund_blocked_reason"] is None
    rest = client.post(f"/api/v2/sites/{site.id}/payments/{order['receipt_id']}/refund", json=_refund_body(200000, "manual-stopped-0001"))
    assert rest.status_code == 200, rest.text
    assert _refunds(db, order["receipt_id"]) == 300000


def test_partial_counter_ticket_approval_can_still_be_rejected(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _manual_timed_order(timed, "partial-reject-ticket-0001")
    request = _request(client, current, users, order["receipt_id"])
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    approved = client.post(url + "/approve", json={"amount": 4000})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    assert _notice(db, f"refund:{request['id']}:approved") == PARTIAL_APPROVED
    detail = client.get(url).json()
    assert detail["entitlement_revoked"] is False and detail["refund_state"]["eligible"] is True
    rejected = client.post(url + "/reject", json={"note": "Khách đổi ý, giữ vé"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected", rejected.text
    db.expire_all()
    assert db.get(TimedParkingPass, order["timed_pass_id"]).status == "ready" and _refunds(db, order["receipt_id"]) == 0


def test_approval_guards_are_unchanged_while_the_car_is_parked(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    period, receipt = _counter_pass(db, users, start=business_now().date(), code="PARKED-APPROVE")
    request = _request(client, current, users, receipt.id)
    vehicle = db.get(Vehicle, period.vehicle_id)
    ParkingService(db).check_in(vehicle.license_plate, kind.id, users[0].id, parking_slot_id=slot.id)
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    for amount in ({}, {"amount": 100000}):
        refused = client.post(url + "/approve", json=amount)
        assert refused.status_code == 409 and refused.json()["detail"] == IN_USE, refused.text
    db.expire_all()
    assert db.get(MonthlyPass, period.id).is_active is True and _refunds(db, receipt.id) == 0


def test_stopped_counter_period_settled_in_site_finance_stays_out_of_the_workflow(portal):
    """Only DEMO money needs the workflow after a stop: Site Finance refunds any other
    stopped period directly, so a negotiated settlement there is not reopened."""
    client, current, users, site, kind, db = portal
    onboard(portal)
    _routes(client)
    period, receipt = _counter_pass(db, users, code="COUNTER-SETTLED")
    current["user"] = users[0]
    assert client.put(f"/api/v1/monthly-passes/{period.id}", json={"is_active": False}).status_code == 200
    assert _site_row(client, site, receipt.id)["direct_refund_blocked_reason"] is None
    settled = client.post(f"/api/v2/sites/{site.id}/payments/{receipt.id}/refund",
        json=_refund_body(150000, "counter-settled-0001"))
    assert settled.status_code == 200, settled.text
    current["user"] = users[1]
    state = _receipt_row(client, receipt.id)["refund"]
    assert state["eligible"] is False and state["blocked_reason"] == "pass_inactive"
    created = client.post(f"/api/v2/me/receipts/{receipt.id}/refund-requests", json={"reason": "Phần còn lại"})
    assert created.status_code == 409, created.text


def test_partial_approval_of_an_old_rule_remainder_promises_no_ticket(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    _routes(client)
    order = _manual_timed_order(timed, "old-partial-notice-0001")
    _old_partial(db, users, order["receipt_id"], 4000, method="cash")
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    ticket.status = "revoked"
    db.get(ParkingReservation, ticket.reservation_id).status = "cancelled"
    db.get(PortalOrder, order["id"]).status = "refunded"
    db.commit()
    request = _request(client, current, users, order["receipt_id"], reason="Phần còn lại")
    approved = client.post(f"/api/v2/sites/{site.id}/refund-requests/{request['id']}/approve", json={"amount": 3000})
    assert approved.status_code == 200 and approved.json()["status"] == "approved", approved.text
    # The earlier rule already revoked the ticket: the generic approval text, not "còn hiệu lực".
    assert _notice(db, f"refund:{request['id']}:approved") == APPROVED
