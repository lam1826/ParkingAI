"""CL-ONLINE fixes 05/10: payOS review evidence can be resolved (#13, #14, #48).

Offline only: fake payOS credentials and an httpx MockTransport (see test_online_payments).
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select

from expansion import online_payment_service as service
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentLink, OnlinePaymentProcessing
from expansion.portal_models import PortalNotification, PortalOrder
from models.payment import Payment

from test_online_payments import online, no_external_payment_configuration, order_and_link, accept, process  # noqa: F401
from test_portal_api import portal, advance_past_order_deadline  # noqa: F401


def _set_clock(monkeypatch, instant):
    import core.clock as clock
    instant = instant.replace(tzinfo=clock.BUSINESS_TZ)

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Frozen)


def _external_refund(ctx, inbox_id, request_id="clonline-refund-0001", reference="CLONLINE-OUT-1"):
    ctx.current["user"] = ctx.users[0]
    route = f"/api/v2/sites/{ctx.site.id}/online-payments/review/{inbox_id}/decisions"
    return ctx.client.post(route, json={"action": "confirmed_external_refund", "request_id": request_id,
        "reason": "Đã hoàn ngoài hệ thống cho khoản cần đối soát", "refund_amount": 300000,
        "external_reference": reference, "confirmed": True})


def _late_review_order(ctx, monkeypatch):
    identity, _ = order_and_link(ctx)
    advance_past_order_deadline(monkeypatch, ctx.db, identity)
    ctx.state["paid"] = True
    event = accept(ctx)
    process(ctx)
    assert ctx.db.get(PortalOrder, identity).status == "review"
    return identity, event


# --- #13 -----------------------------------------------------------------

def test_reviewed_payos_order_does_not_lock_vehicle_out_of_new_orders(online, monkeypatch):
    _late_review_order(online, monkeypatch)
    online.current["user"] = online.users[1]
    response = online.client.post("/api/v2/me/orders", json={**online.body, "payment_mode": "manual",
        "idempotency_key": "clonline-after-review-1"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"


def test_external_refund_closes_reviewed_payos_order_and_notifies_customer(online, monkeypatch):
    identity, event = _late_review_order(online, monkeypatch)
    decision = _external_refund(online, event.id)
    assert decision.status_code == 200, decision.text
    online.db.expire_all()
    order = online.db.get(PortalOrder, identity)
    assert order.status == "cancelled"
    assert online.db.scalar(select(PortalNotification).where(
        PortalNotification.event_key == f"order:{identity}:review-closed")) is not None
    # Evidence stays durable review evidence; no receipt is invented.
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "review"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0
    online.current["user"] = online.users[1]
    view = online.client.get(f"/api/v2/me/orders/{identity}/payment-link").json()
    assert "hoàn" in view["message"] and view["can_refresh"] is False


def test_demo_review_order_still_waits_for_manager_decision(portal):
    from test_portal_api import onboard
    from expansion.portal_models import PortalPaymentEvent
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    row = db.get(PortalOrder, order["id"])
    row.status, row.review_reason = "review", "late_payment"
    db.add(PortalPaymentEvent(order_id=row.id, reference="demo:" + row.id, outcome="success",
        amount=row.amount, status="review"))
    db.commit()
    retry = client.post("/api/v2/me/orders", json={**body, "idempotency_key": "clonline-demo-2"})
    assert retry.status_code == 409


# --- #14 -----------------------------------------------------------------

def _settle_then_extra(ctx):
    identity, _ = order_and_link(ctx)
    ctx.state["paid"] = True
    accept(ctx)
    process(ctx)
    order = ctx.db.get(PortalOrder, identity)
    assert order.status == "fulfilled"
    extra = accept(ctx, reference="OFFLINE-TX-EXTRA")
    process(ctx)
    assert ctx.db.get(OnlinePaymentProcessing, extra.id).reason == "additional_payment"
    return identity, order.receipt_id, extra


def test_additional_transfer_keeps_settled_link_paid(online):
    identity, _, _ = _settle_then_extra(online)
    link = online.db.scalar(select(OnlinePaymentLink))
    assert link.state == "paid"
    online.current["user"] = online.users[1]
    view = online.client.get(f"/api/v2/me/orders/{identity}/payment-link").json()
    assert view["state"] == "paid" and view["can_refresh"] is False
    assert "chuyển thêm" in view["message"]


def test_extra_transfer_reconciliation_clears_after_external_refund(online):
    _, _, extra = _settle_then_extra(online)
    link = online.db.scalar(select(OnlinePaymentLink))
    assert service.link_under_reconciliation(online.db, link) is True
    assert _external_refund(online, extra.id).status_code == 200
    online.db.expire_all()
    link = online.db.scalar(select(OnlinePaymentLink))
    assert service.link_under_reconciliation(online.db, link) is False


def test_original_receipt_refundable_after_extra_transfer_is_refunded(online):
    from expansion.support_router import router as support_router
    online.client.app.include_router(support_router, prefix="/api/v2")
    _, receipt_id, extra = _settle_then_extra(online)
    online.current["user"] = online.users[1]
    rows = online.client.get("/api/v2/me/receipts").json()["items"]
    before = next(row for row in rows if row["id"] == receipt_id)["refund"]
    assert before["blocked_reason"] == "under_reconciliation"
    assert _external_refund(online, extra.id).status_code == 200
    online.current["user"] = online.users[1]
    rows = online.client.get("/api/v2/me/receipts").json()["items"]
    after = next(row for row in rows if row["id"] == receipt_id)["refund"]
    assert after["eligible"] is True and after["refundable_amount"] == 300000


def _provider_mismatch_refresh(ctx, monkeypatch, identity):
    from core.clock import business_now
    _set_clock(monkeypatch, business_now() + timedelta(seconds=15))
    ctx.state["amount"] = ctx.state["amount"] + 1  # provider GET now reports another amount
    ctx.current["user"] = ctx.users[1]
    response = ctx.client.post(f"/api/v2/me/orders/{identity}/payment-link/refresh")
    assert response.status_code == 200, response.text
    ctx.db.expire_all()
    link = ctx.db.scalar(select(OnlinePaymentLink))
    assert link.state == "review" and link.receipt_id is not None
    return link


def test_paid_link_moved_to_review_by_provider_mismatch_still_blocks_refund(online, monkeypatch):
    """Rework of #14: a settled link put in review by a provider mismatch has no review
    evidence row, yet must keep blocking refunds of its receipt (before and after R1)."""
    from expansion.support_router import router as support_router
    online.client.app.include_router(support_router, prefix="/api/v2")
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    accept(online)
    process(online)
    order = online.db.get(PortalOrder, identity)
    assert order.status == "fulfilled"
    receipt_id = order.receipt_id
    link = _provider_mismatch_refresh(online, monkeypatch, identity)
    assert service.link_under_reconciliation(online.db, link) is True
    online.current["user"] = online.users[1]
    rows = online.client.get("/api/v2/me/receipts").json()["items"]
    refund = next(row for row in rows if row["id"] == receipt_id)["refund"]
    assert refund["eligible"] is False and refund["blocked_reason"] == "under_reconciliation"


def test_resolved_extra_transfer_does_not_clear_a_later_provider_mismatch(online, monkeypatch):
    _, _, extra = _settle_then_extra(online)
    assert _external_refund(online, extra.id).status_code == 200
    online.db.expire_all()
    link = online.db.scalar(select(OnlinePaymentLink))
    assert service.link_under_reconciliation(online.db, link) is False
    link = _provider_mismatch_refresh(online, monkeypatch, link.order_id)
    assert service.link_under_reconciliation(online.db, link) is True
    view = online.client.get(f"/api/v2/me/orders/{link.order_id}/payment-link").json()
    assert view["state"] == "review" and "hoàn khoản chuyển này" not in view["message"]


# --- #48 -----------------------------------------------------------------

def test_customer_refresh_of_reviewed_transfer_creates_no_twin_evidence(online, monkeypatch):
    from core.clock import business_now
    identity, _ = _late_review_order(online, monkeypatch)
    _set_clock(monkeypatch, business_now() + timedelta(seconds=15))
    online.current["user"] = online.users[1]
    response = online.client.post(f"/api/v2/me/orders/{identity}/payment-link/refresh")
    assert response.status_code == 200, response.text
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 1


def test_one_external_refund_resolves_every_evidence_row_of_the_same_transfer(online, monkeypatch):
    identity, _ = order_and_link(online)
    advance_past_order_deadline(monkeypatch, online.db, identity)
    online.state["paid"] = True
    process(online)  # worker GET records the transfer first (source=reconcile)
    accept(online)   # the delayed signed webhook for the same transfer
    process(online)
    rows = online.db.execute(select(OnlinePaymentInbox, OnlinePaymentProcessing).join(
        OnlinePaymentProcessing, OnlinePaymentProcessing.id == OnlinePaymentInbox.id)).all()
    assert sorted(processing.status for _, processing in rows) == ["review", "review"]
    online.current["user"] = online.users[0]
    base = f"/api/v2/sites/{online.site.id}/online-payments/review"
    items = online.client.get(base).json()["items"]
    assert len(items) == 2 and all(len(item["same_reference_ids"]) == 1 for item in items)
    assert _external_refund(online, items[0]["id"]).status_code == 200
    items = online.client.get(base).json()["items"]
    assert {item["resolution"] for item in items} == {"external_refund_recorded"}
