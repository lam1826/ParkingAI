"""Real payOS orchestration with fake credentials and a fully offline transport."""
import json
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.clock import business_now
from expansion import online_payment_service as service
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentLink, OnlinePaymentProcessing, OnlinePaymentReviewDecision
from expansion.online_payment_router import router, get_payos_gateway
from expansion.online_payment_schemas import OnlinePaymentConfig, get_online_payment_config
from expansion.online_payment_worker import run_online_payment_maintenance
from expansion.payos_gateway import PayOSGateway
from expansion.portal_models import PortalOrder, PortalPaymentEvent
from models.monthly_pass import MonthlyPass
from models.payment import Payment


@pytest.fixture(autouse=True)
def no_external_payment_configuration(monkeypatch):
    for name in OnlinePaymentConfig.model_fields:
        monkeypatch.delenv(name, raising=False)

from test_portal_api import portal, onboard, advance_past_order_deadline  # noqa: F401
from test_payos_gateway import ACCOUNT, LINK_ID, PUBLIC_EXAMPLE_CHECKSUM, created_data, link_data, signed, transaction


@pytest.fixture
def online(portal, monkeypatch):
    client, current, users, site, kind, db = portal
    config = OnlinePaymentConfig(_env_file=None, PAYOS_ENABLED=True, PAYOS_CLIENT_ID="FAKE_CLIENT_ID",
        PAYOS_API_KEY="FAKE_API_KEY", PAYOS_CHECKSUM_KEY=PUBLIC_EXAMPLE_CHECKSUM,
        PAYOS_RECEIVER_ACCOUNT_NUMBER=ACCOUNT, PAYOS_SITE_ID=site.id,
        PAYOS_RETURN_URL="https://parking.example/payment-return", PAYOS_CANCEL_URL="https://parking.example/payment-cancel")
    monkeypatch.setattr(service, "get_online_payment_config", lambda: config)
    client.app.include_router(router, prefix="/api/v2")
    client.app.dependency_overrides[get_online_payment_config] = lambda: config
    state = {"paid": False, "calls": [], "reference": "OFFLINE-TX-1"}

    def transport(request):
        assert not db.in_transaction(), "HTTP must never run inside the application's SQL transaction"
        state["calls"].append((request.method, request.url.path))
        if state.get("fail"):
            raise httpx.ReadTimeout("offline timeout", request=request)
        if request.method == "POST" and not request.url.path.endswith("/cancel"):
            body = json.loads(request.content)
            state.update(code=body["orderCode"], amount=body["amount"], expires=body["expiredAt"])
            with Session(db.get_bind()) as independent:
                persisted = independent.get(OnlinePaymentLink, state["code"])
                assert persisted is not None and persisted.amount == state["amount"]
            return httpx.Response(200, json=signed(created_data(orderCode=state["code"], amount=state["amount"],
                expiredAt=state["expires"], description=body["description"])))
        entries = state.get("transactions", [transaction(amount=state["amount"], reference=state["reference"])] if state["paid"] else [])
        paid = sum(entry["amount"] for entry in entries)
        status = state.get("status", "PAID" if state["paid"] else "PENDING")
        if request.url.path.endswith("/cancel") and not paid:
            status = "CANCELLED"
        return httpx.Response(200, json=signed(link_data(orderCode=state["code"], amount=state["amount"],
            amountPaid=paid, amountRemaining=max(0, state["amount"] - paid), transactions=entries, status=status)))

    with httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as transport_client:
        gateway = PayOSGateway(config.adapter_settings(), transport_client)
        client.app.dependency_overrides[get_payos_gateway] = lambda: gateway
        body = onboard(portal)
        yield SimpleNamespace(client=client, current=current, users=users, site=site, db=db, body=body,
            config=config, gateway=gateway, state=state, portal=portal)


def order_and_link(ctx):
    response = ctx.client.post("/api/v2/me/orders", json={**ctx.body, "payment_mode": "payos"})
    assert response.status_code == 200, response.text
    identity = response.json()["id"]
    response = ctx.client.post(f"/api/v2/me/orders/{identity}/payment-link")
    assert response.status_code == 200, response.text
    return identity, response.json()


def webhook_bytes(ctx, **changes):
    data = {"orderCode": ctx.state["code"], "paymentLinkId": LINK_ID, "amount": ctx.state["amount"],
        "currency": "VND", "accountNumber": ACCOUNT, "reference": ctx.state["reference"],
        "description": "OFFLINE PARKING", "transactionDateTime": "2026-09-15 10:30:00",
        "code": "00", "desc": "Success", **changes}
    return json.dumps(signed(data, success=True), ensure_ascii=False).encode()


def accept(ctx, **changes):
    response = ctx.client.post("/api/v2/payments/payos/webhook", content=webhook_bytes(ctx, **changes))
    assert response.status_code == 200, response.text
    assert response.json() == {"success": True}
    return ctx.db.scalar(select(OnlinePaymentInbox).order_by(OnlinePaymentInbox.received_at.desc()))


def process(ctx):
    result = run_online_payment_maintenance(ctx.db, ctx.config, ctx.gateway)
    assert result["retry"] == 0
    return result


def test_mapping_committed_before_create_and_never_resubmitted(online):
    identity, view = order_and_link(online)
    assert view["state"] == "ready" and view["qr_code"] == "FAKE_QR_PAYLOAD"
    assert view["amount"] == 300000 and view["can_create"] is False
    second = online.client.post(f"/api/v2/me/orders/{identity}/payment-link")
    assert second.json()["state"] == "ready"
    assert len(online.state["calls"]) == 1
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_webhook_commits_before_ack_and_worker_issues_exactly_one_real_receipt(online):
    identity, _ = order_and_link(online)
    event = accept(online)
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "received"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0
    assert len(online.state["calls"]) == 1, "webhook verification must be offline"
    online.state["paid"] = True
    process(online)
    order = online.db.get(PortalOrder, identity)
    receipt = online.db.get(Payment, order.receipt_id)
    assert order.status == "fulfilled" and receipt.amount == 300000
    assert receipt.method == "transfer" and receipt.collected_by_id is None and receipt.shift_id is None
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "processed"
    assert online.db.scalar(select(func.count()).select_from(MonthlyPass)) == 1
    assert online.db.scalar(select(func.count()).select_from(PortalPaymentEvent)) == 0
    accept(online)
    process(online)
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 1
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 1


def test_missed_webhook_recovered_from_signed_get_with_durable_evidence(online):
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    online.db.query(OnlinePaymentLink).update({OnlinePaymentLink.last_checked_at: None})
    online.db.commit()
    response = online.client.post(f"/api/v2/me/orders/{identity}/payment-link/refresh")
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "paid"
    assert online.db.scalar(select(OnlinePaymentInbox)).source == "reconcile"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 1


@pytest.mark.parametrize("changes,reason", [
    ({"amount": 299999}, "payment_identity_mismatch"),
    ({"currency": "USD"}, "currency_mismatch"),
    ({"accountNumber": "99999999"}, "account_mismatch"),
    ({"paymentLinkId": "OTHER-LINK"}, "provider_identity_mismatch"),
])
def test_signed_financial_mismatch_preserved_without_entitlement(online, changes, reason):
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    event = accept(online, **changes)
    process(online)
    assert online.db.get(OnlinePaymentProcessing, event.id).reason == reason
    assert online.db.get(PortalOrder, identity).status == "review"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0
    assert online.db.scalar(select(func.count()).select_from(MonthlyPass)) == 0


def test_signed_unknown_order_is_acknowledged_and_retained_for_site_manager(online):
    order_and_link(online)
    event = accept(online, orderCode=999999)
    assert event.link_id is None
    assert online.db.get(OnlinePaymentProcessing, event.id).reason == "unknown_order"
    calls = len(online.state["calls"])
    process(online)
    assert len(online.state["calls"]) == calls
    online.current["user"] = online.users[0]
    response = online.client.get(f"/api/v2/sites/{online.site.id}/online-payments/review")
    assert response.status_code == 200 and response.json()["items"][0]["order_id"] is None


def test_new_reference_after_fulfilled_is_review_not_second_receipt(online):
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    accept(online)
    process(online)
    accept(online, reference="OFFLINE-TX-EXTRA")
    process(online)
    states = list(online.db.scalars(select(OnlinePaymentProcessing)))
    assert {row.status for row in states} == {"processed", "review"}
    assert any(row.reason == "additional_payment" for row in states)
    assert online.db.get(PortalOrder, identity).status == "fulfilled"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 1
    assert online.db.scalar(select(func.count()).select_from(MonthlyPass)) == 1


def test_conflicting_reference_evidence_is_never_overwritten(online):
    order_and_link(online)
    online.state["paid"] = True
    first = accept(online)
    first_id, digest = first.id, first.payload_digest
    accept(online, amount=300001)
    process(online)
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 2
    assert online.db.get(OnlinePaymentInbox, first_id).payload_digest == digest
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_late_payment_is_review_and_does_not_issue(online, monkeypatch):
    identity, _ = order_and_link(online)
    advance_past_order_deadline(monkeypatch, online.db, identity)
    online.state["paid"] = True
    event = accept(online)
    process(online)
    assert online.db.get(OnlinePaymentProcessing, event.id).reason == "late_or_closed_order"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_paused_site_still_retains_signed_money_but_cannot_fulfill(online):
    order_and_link(online)
    online.site.is_active = False
    online.db.commit()
    online.state["paid"] = True
    event = accept(online)
    process(online)
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "review"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_owner_bounds_and_no_browser_confirmation(online):
    identity, _ = order_and_link(online)
    online.current["user"] = online.users[2]
    assert online.client.get(f"/api/v2/me/orders/{identity}/payment-link").status_code == 404
    assert online.client.post(f"/api/v2/me/orders/{identity}/payment-link/refresh").status_code == 404
    assert online.client.get(f"/api/v2/sites/{online.site.id}/online-payments/review").status_code == 403
    online.current["user"] = online.users[1]
    response = online.client.get(f"/api/v2/me/orders/{identity}/payment-link?status=PAID&cancel=false")
    assert response.json()["state"] == "ready"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_direct_legacy_cancel_cannot_leave_payos_link_active(online):
    identity, _ = order_and_link(online)
    response = online.client.post(f"/api/v2/me/orders/{identity}/cancel")
    assert response.status_code == 409
    assert online.db.get(PortalOrder, identity).status == "pending"


def test_cancel_requires_verified_provider_response_and_releases_order(online):
    identity, _ = order_and_link(online)
    online.db.query(OnlinePaymentLink).update({OnlinePaymentLink.last_checked_at: None})
    online.db.commit()
    response = online.client.post(f"/api/v2/me/orders/{identity}/payment-link/cancel", json={"reason": "Không cần vé nữa"})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "cancelled"
    assert online.db.get(PortalOrder, identity).status == "cancelled"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_unknown_create_outcome_uses_same_mapping_without_post_retry(online):
    response = online.client.post("/api/v2/me/orders", json={**online.body, "payment_mode": "payos"})
    assert response.status_code == 200, response.text
    identity = response.json()["id"]
    online.state["fail"] = True
    first = online.client.post(f"/api/v2/me/orders/{identity}/payment-link")
    assert first.status_code == 200 and first.json()["state"] == "unknown"
    second = online.client.post(f"/api/v2/me/orders/{identity}/payment-link")
    assert second.json()["state"] == "unknown" and len(online.state["calls"]) == 1
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1


def test_invalid_signature_and_oversized_body_create_no_inbox(online):
    order_and_link(online)
    raw = json.loads(webhook_bytes(online))
    raw["signature"] = "0" * 64
    assert online.client.post("/api/v2/payments/payos/webhook", json=raw).status_code == 400
    assert online.client.post("/api/v2/payments/payos/webhook", content=b"x" * 65537).status_code == 413
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 0


@pytest.mark.parametrize("sql", [
    "UPDATE online_payment_inbox SET amount=1", "DELETE FROM online_payment_inbox",
    "INSERT OR REPLACE INTO online_payment_inbox SELECT * FROM online_payment_inbox",
    "UPDATE online_payment_links SET amount=1", "UPDATE online_payment_links SET order_id='other'",
    "DELETE FROM online_payment_links", "INSERT OR REPLACE INTO online_payment_links SELECT * FROM online_payment_links",
    "DELETE FROM portal_orders", "DELETE FROM online_payment_processing",
])
def test_database_retains_financial_identity_and_evidence(online, sql):
    order_and_link(online)
    accept(online)
    with pytest.raises(IntegrityError):
        online.db.execute(text(sql))
        online.db.commit()
    online.db.rollback()
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 1
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1


def test_disabled_configuration_never_calls_provider(online):
    identity, _ = order_and_link(online)
    disabled = OnlinePaymentConfig(_env_file=None, PAYOS_ENABLED=False)
    online.client.app.dependency_overrides[get_online_payment_config] = lambda: disabled
    online.client.app.dependency_overrides.pop(get_payos_gateway)
    calls = len(online.state["calls"])
    response = online.client.get(f"/api/v2/me/orders/{identity}/payment-link")
    assert response.status_code == 200 and response.json()["enabled"] is False
    assert response.json()["qr_code"] is None
    assert online.client.post(f"/api/v2/me/orders/{identity}/payment-link").status_code == 503
    assert run_online_payment_maintenance(online.db, disabled, online.gateway)["disabled"] is True
    assert len(online.state["calls"]) == calls


@pytest.mark.parametrize("status,paid", [("PENDING", False), ("PROCESSING", False), ("PENDING", True), ("PROCESSING", True)])
def test_eventual_provider_projection_retries_then_fulfills(online, status, paid):
    identity, _ = order_and_link(online)
    event = accept(online)
    online.state.update(status=status, paid=paid)
    process(online)
    processing = online.db.get(OnlinePaymentProcessing, event.id)
    assert processing.status == "received" and processing.reason == "provider_settlement_pending"
    assert processing.next_attempt_at > business_now()
    assert online.db.get(PortalOrder, identity).status == "pending"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0
    online.state.update(status="PAID", paid=True)
    service.process_inbox(online.db, event.id, online.config, online.gateway)
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "processed"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 1


def test_worker_recovers_lost_webhook_without_customer_refresh(online):
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    online.db.query(OnlinePaymentLink).update({OnlinePaymentLink.last_checked_at: None})
    online.db.commit()
    result = process(online)
    assert result["reconciled"] == 1
    assert online.db.get(PortalOrder, identity).status == "fulfilled"
    assert online.db.scalar(select(OnlinePaymentInbox)).source == "reconcile"


def test_worker_recovers_expired_create_lease_by_get_never_create(online):
    identity, _ = order_and_link(online)
    row = online.db.scalar(select(OnlinePaymentLink))
    row.state, row.operation_token = "creating", "crashed-process"
    row.operation_until, row.last_checked_at = business_now() - timedelta(seconds=1), None
    online.db.commit()
    online.state["paid"] = True
    process(online)
    assert online.db.get(PortalOrder, identity).status == "fulfilled"
    assert sum(method == "POST" for method, _ in online.state["calls"]) == 1


def test_provider_unavailable_after_expiry_becomes_durable_review(online, monkeypatch):
    identity, _ = order_and_link(online)
    event = accept(online)
    advance_past_order_deadline(monkeypatch, online.db, identity)
    online.state["fail"] = True
    process(online)
    assert online.db.get(OnlinePaymentProcessing, event.id).reason == "provider_unavailable_after_expiry"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_webhook_commit_failure_never_acknowledges_or_loses_retry(online, monkeypatch):
    order_and_link(online)
    original = online.db.commit

    def failed_commit():
        raise RuntimeError("offline injected database outage")

    monkeypatch.setattr(online.db, "commit", failed_commit)
    with pytest.raises(RuntimeError, match="offline injected"):
        online.client.post("/api/v2/payments/payos/webhook", content=webhook_bytes(online))
    monkeypatch.setattr(online.db, "commit", original)
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 0
    accept(online)
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentInbox)) == 1


def test_fulfillment_failure_rolls_back_receipt_and_retries_from_inbox(online, monkeypatch):
    identity, _ = order_and_link(online)
    event = accept(online)
    online.state["paid"] = True
    original = service.portal_service._fulfill

    def crash_after_fulfill(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("offline crash after receipt")

    monkeypatch.setattr(service.portal_service, "_fulfill", crash_after_fulfill)
    result = run_online_payment_maintenance(online.db, online.config, online.gateway)
    assert result["retry"] >= 1
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0
    assert online.db.scalar(select(func.count()).select_from(MonthlyPass)) == 0
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "received"
    monkeypatch.setattr(service.portal_service, "_fulfill", original)
    service.process_inbox(online.db, event.id, online.config, online.gateway)
    assert online.db.get(PortalOrder, identity).status == "fulfilled"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 1


def test_partial_or_multiple_transfers_require_review_without_automatic_combination(online):
    order_and_link(online)
    online.state.update(paid=True, transactions=[transaction(amount=150000), transaction(amount=150000, reference="OFFLINE-TX-2")])
    accept(online)
    process(online)
    assert online.db.scalar(select(OnlinePaymentProcessing)).reason == "payment_total_requires_review"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


def review_case(ctx):
    order_and_link(ctx)
    event = accept(ctx, orderCode=999999)
    ctx.current["user"] = ctx.users[0]
    return event.id, f"/api/v2/sites/{ctx.site.id}/online-payments/review/{event.id}/decisions"


def external_refund(**changes):
    return {"action": "confirmed_external_refund", "request_id": "external-refund-0001",
        "reason": "Đã kiểm tra giao dịch và hoàn ngoài hệ thống", "refund_amount": 300000,
        "external_reference": "OFFLINE-OUTGOING-1", "confirmed": True, **changes}


def test_review_decisions_are_append_only_exact_replay_and_refund_once(online):
    identity, route = review_case(online)
    note = online.client.post(route, json={"action": "note", "request_id": "review-note-0001", "reason": "Đang đối chiếu chứng từ"})
    assert note.status_code == 200, note.text
    body = external_refund()
    response = online.client.post(route, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["refund_amount"] == 300000
    replay = online.client.post(route, json=body)
    assert replay.status_code == 200 and replay.json()["id"] == response.json()["id"]
    assert online.client.post(route, json={**body, "reason": "Lý do khác"}).status_code == 409
    assert online.client.post(route, json=external_refund(request_id="external-refund-0002", external_reference="ANOTHER-OUTGOING")).status_code == 409
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentReviewDecision)) == 2
    assert online.db.get(OnlinePaymentProcessing, identity).status == "review"
    assert online.db.scalar(select(func.count()).select_from(Payment)) == 0, "A manager note is not a fabricated ledger receipt"
    listing = online.client.get(f"/api/v2/sites/{online.site.id}/online-payments/review").json()["items"]
    assert listing[0]["resolution"] == "external_refund_recorded" and len(listing[0]["decisions"]) == 2


@pytest.mark.parametrize("changes,status", [({"refund_amount": 1}, 409), ({"confirmed": False}, 422),
    ({"refund_amount": True}, 422), ({"external_reference": None}, 422)])
def test_review_refund_requires_matching_amount_and_explicit_external_evidence(online, changes, status):
    _, route = review_case(online)
    assert online.client.post(route, json=external_refund(**changes)).status_code == status
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentReviewDecision)) == 0


@pytest.mark.parametrize("sql", ["UPDATE online_payment_review_decisions SET reason='changed'",
    "DELETE FROM online_payment_review_decisions",
    "INSERT OR REPLACE INTO online_payment_review_decisions SELECT * FROM online_payment_review_decisions"])
def test_database_review_decisions_cannot_be_changed_or_replaced(online, sql):
    _, route = review_case(online)
    assert online.client.post(route, json=external_refund()).status_code == 200
    with pytest.raises(IntegrityError):
        online.db.execute(text(sql))
        online.db.commit()
    online.db.rollback()
    assert online.db.scalar(select(func.count()).select_from(OnlinePaymentReviewDecision)) == 1


def test_review_requires_global_and_site_manager_roles(online):
    from expansion.site_models import SiteMembership
    from models.role import Role
    from models.user import User

    _, route = review_case(online)
    role = Role(name="manager")
    online.db.add(role)
    online.db.flush()
    actor = User(username="online-review-manager", full_name="Online manager", password_hash="unused", role_id=role.id, is_active=True)
    online.db.add(actor)
    online.db.flush()
    membership = SiteMembership(user_id=actor.id, site_id=online.site.id, role="staff")
    online.db.add(membership)
    online.db.commit()
    online.current["user"] = actor
    assert online.client.post(route, json=external_refund()).status_code == 403
    membership.role = "manager"
    online.db.commit()
    assert online.client.post(route, json=external_refund()).status_code == 200


@pytest.mark.parametrize("outcome", ["paid", "cancel", "late"])
def test_timed_payos_uses_same_atomic_hold_entitlement_and_receipt(online, outcome, monkeypatch):
    from core.clock import BUSINESS_TZ
    from expansion.timed_parking_models import ParkingCapacityHold, TimedParkingPass
    from models.zone import Zone
    from models.parking_slot import ParkingSlot
    from models.price_config import PriceConfig

    kind = online.portal[4]
    zone = Zone(name="Online zone", capacity=1, is_active=True, site_id=online.site.id)
    online.db.add(zone)
    online.db.flush()
    slot = ParkingSlot(slot_name="ONLINE-1", zone_id=zone.id, vehicle_type_id=kind.id, is_active=True, is_occupied=False)
    rate = PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=5000,
        effective_date=business_now().date(), is_active=True)
    online.db.add_all([slot, rate])
    online.site.customer_booking_mode = "paid_packages"
    online.db.commit()
    online.current["user"] = online.users[0]
    response = online.client.post("/api/v2/portal/admin/plans", json={"name": "Online two hours", "site_id": online.site.id,
        "vehicle_type_id": kind.id, "product_kind": "hourly", "duration_minutes": 120, "price": 12000})
    assert response.status_code == 200, response.text
    online.body.update(plan_id=response.json()["id"],
        start_at=(business_now() + timedelta(minutes=2)).replace(tzinfo=BUSINESS_TZ).isoformat())
    online.current["user"] = online.users[1]
    identity, _ = order_and_link(online)
    if outcome == "cancel":
        online.db.query(OnlinePaymentLink).update({OnlinePaymentLink.last_checked_at: None})
        online.db.commit()
        response = online.client.post(f"/api/v2/me/orders/{identity}/payment-link/cancel", json={"reason": "Không cần nữa"})
        assert response.status_code == 200, response.text
        assert online.db.scalar(select(ParkingCapacityHold)).status == "released"
        assert online.db.scalar(select(func.count()).select_from(TimedParkingPass)) == 0
    else:
        if outcome == "late":
            advance_past_order_deadline(monkeypatch, online.db, identity)
        online.state["paid"] = True
        accept(online)
        process(online)
        if outcome == "paid":
            order = online.db.get(PortalOrder, identity)
            receipt = online.db.get(Payment, order.receipt_id)
            assert receipt.source_type == "portal_order" and receipt.source_id == order.id
            assert receipt.method == "transfer" and receipt.collected_by_id is None
            assert receipt.amount == 12000
            assert online.db.scalar(select(ParkingCapacityHold)).status == "converted"
            assert online.db.scalar(select(func.count()).select_from(TimedParkingPass)) == 1
        else:
            assert online.db.scalar(select(ParkingCapacityHold)).status == "expired"
            assert online.db.scalar(select(func.count()).select_from(TimedParkingPass)) == 0
            assert online.db.scalar(select(func.count()).select_from(Payment)) == 0


@pytest.mark.parametrize("changes", [{"currency": "USD"}, {"accountNumber": "99999999"}])
def test_manager_cannot_record_refund_for_wrong_currency_or_receiver(online, changes):
    order_and_link(online)
    event = accept(online, **changes)
    process(online)
    online.current["user"] = online.users[0]
    route = f"/api/v2/sites/{online.site.id}/online-payments/review/{event.id}/decisions"
    assert online.client.post(route, json=external_refund()).status_code == 409
    note = online.client.post(route, json={"action": "note", "request_id": "wrong-currency-note", "reason": "Đang kiểm tra sai tài khoản hoặc đơn vị tiền"})
    assert note.status_code == 200, note.text


def test_payos_order_without_provider_mapping_can_cancel_locally(online):
    response = online.client.post("/api/v2/me/orders", json={**online.body, "payment_mode": "payos"})
    assert response.status_code == 200, response.text
    identity = response.json()["id"]
    assert "cancel" in response.json()["allowed_actions"]
    listing = online.client.get("/api/v2/me/orders").json()["items"]
    assert "cancel" in next(order for order in listing if order["id"] == identity)["allowed_actions"]
    cancelled = online.client.post(f"/api/v2/me/orders/{identity}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert online.state["calls"] == []


def test_cancel_immediately_after_create_is_not_suppressed_by_get_throttle(online):
    identity, view = order_and_link(online)
    assert view["can_cancel"] is True
    listing = online.client.get("/api/v2/me/orders").json()["items"]
    assert "cancel" not in next(order for order in listing if order["id"] == identity)["allowed_actions"]
    cancelled = online.client.post(f"/api/v2/me/orders/{identity}/payment-link/cancel", json={"reason": "Không cần vé nữa"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    assert online.state["calls"][-1][1].endswith("/cancel")
