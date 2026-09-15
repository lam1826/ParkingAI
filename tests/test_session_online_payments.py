"""Accrued-fee online credits preserve physical occupancy and exact ledger totals."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ, business_now, day_bounds
from expansion import online_payment_service
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentLink, OnlinePaymentProcessing
from expansion.online_payment_router import get_payos_gateway
from expansion.online_payment_schemas import OnlinePaymentConfig, get_online_payment_config
from expansion.online_payment_worker import run_online_payment_maintenance
from expansion.payos_gateway import PayOSGateway
from expansion.session_payment_models import SessionFeeCredit, SessionFeeQuote
from expansion.session_payment_router import router
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.payment import Payment
from models.price_config import PriceConfig
from models.vehicle import Vehicle
from models.zone import Zone
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from services.payment_service import PaymentService

from test_online_payments import online, no_external_payment_configuration  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_payos_gateway import ACCOUNT, created_data, link_data, signed, transaction
from test_session_exceptions import env as exception_env  # noqa: F401


@pytest.fixture
def parking_online(online, monkeypatch):
    import core.clock as clock
    monkeypatch.delenv("SESSION_FEE_QUOTE_TTL_SECONDS", raising=False)
    instant = [business_now().replace(microsecond=0) + timedelta(seconds=1)]
    base = instant[0]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = instant[0].replace(tzinfo=BUSINESS_TZ)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Clock)
    db, kind = online.db, online.portal[4]
    zone = Zone(name="Online session zone", capacity=1, site_id=online.site.id, is_active=True)
    db.add(zone)
    db.flush()
    slot = ParkingSlot(slot_name="SESSION-1", zone_id=zone.id, vehicle_type_id=kind.id, is_active=True, is_occupied=False)
    rate = PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=5000, effective_date=base.date(), is_active=True)
    db.add_all([slot, rate])
    db.commit()
    vehicle = db.get(Vehicle, online.body["vehicle_id"])
    result = ParkingService(db).check_in(vehicle.license_plate, kind.id, online.users[0].id, parking_slot_id=slot.id)
    session_id = result["session_id"]
    online.client.app.include_router(router, prefix="/api/v2")
    provider = {"links": {}, "calls": []}

    def handler(request):
        assert not db.in_transaction(), "No provider HTTP under a SQL transaction"
        provider["calls"].append((request.method, request.url.path))
        if request.method == "POST" and not request.url.path.endswith("/cancel"):
            body = json.loads(request.content)
            code = body["orderCode"]
            identity = f"OFFLINE-SESSION-{code}"
            provider["links"][code] = {"amount": body["amount"], "id": identity, "paid": False, "reference": f"OFFLINE-TX-{code}"}
            return httpx.Response(200, json=signed(created_data(orderCode=code, amount=body["amount"],
                paymentLinkId=identity, checkoutUrl=f"https://pay.payos.vn/web/{identity}", description=body["description"],
                expiredAt=body["expiredAt"])))
        code = int(request.url.path.rstrip("/").split("/")[-2 if request.url.path.endswith("/cancel") else -1])
        state = provider["links"][code]
        amount = state["amount"]
        entries = [transaction(amount=amount, reference=state["reference"])] if state["paid"] else []
        status = state.get("status", "PAID" if state["paid"] else "CANCELLED" if request.url.path.endswith("/cancel") else "PENDING")
        return httpx.Response(200, json=signed(link_data(id=state["id"], orderCode=code, amount=amount,
            amountPaid=amount if entries else 0, amountRemaining=0 if entries else amount, transactions=entries, status=status)))

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as transport:
        gateway = PayOSGateway(online.config.adapter_settings(), transport)
        online.client.app.dependency_overrides[get_payos_gateway] = lambda: gateway
        instant[0] = base + timedelta(minutes=70)
        yield SimpleNamespace(**vars(online), clock=instant, base=base, session_id=session_id, slot=slot,
            provider=provider, fee_gateway=gateway)


def status(ctx):
    response = ctx.client.get(f"/api/v2/me/sessions/{ctx.session_id}/payment-status")
    assert response.status_code == 200, response.text
    return response.json()


def quote(ctx, request_id="session-quote-0001"):
    response = ctx.client.post(f"/api/v2/me/sessions/{ctx.session_id}/payment-quote", json={"request_id": request_id})
    assert response.status_code == 200, response.text
    return response.json()


def link(ctx, proposal):
    response = ctx.client.post(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link")
    assert response.status_code == 200, response.text
    assert response.json()["quote_id"] == proposal["id"] and response.json()["order_id"] is None
    return ctx.db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.session_quote_id == proposal["id"])).id


def receive(ctx, code):
    state = ctx.provider["links"][code]
    state["paid"] = True
    data = {"orderCode": code, "paymentLinkId": state["id"], "amount": state["amount"], "currency": "VND",
        "accountNumber": ACCOUNT, "reference": state["reference"], "description": "OFFLINE PARKING FEE",
        "transactionDateTime": "2026-09-15 10:30:00", "code": "00", "desc": "Success"}
    response = ctx.client.post("/api/v2/payments/payos/webhook", json=signed(data, success=True))
    assert response.status_code == 200, response.text
    return ctx.db.scalar(select(OnlinePaymentInbox).where(OnlinePaymentInbox.order_code == code,
        OnlinePaymentInbox.source == "webhook")).id


def settle(ctx, code):
    identity = receive(ctx, code)
    result = run_online_payment_maintenance(ctx.db, ctx.config, ctx.fee_gateway)
    assert result["retry"] == 0
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == "processed"


def checkout(ctx, *, method=None, prior=None):
    actor = ctx.users[0].id
    proposal = prior or CheckoutService(ctx.db).quote(ctx.session_id, actor)
    return CheckoutService(ctx.db).confirm(CheckoutConfirmation(quote_token=proposal["quote_token"],
        payment_confirmed=True, payment_method=method), actor, session_id=ctx.session_id)


def test_quote_uses_tariff_block_end_separate_from_five_minute_expiry(parking_online):
    ctx = parking_online
    result = status(ctx)
    assert result["gross_fee"] == 10000 and result["online_paid"] == 0 and result["balance_due"] == 10000
    proposal = quote(ctx)
    assert proposal["balance_due"] == 10000
    assert datetime.fromisoformat(proposal["paid_through"]).replace(tzinfo=None) == ctx.base + timedelta(hours=2)
    assert datetime.fromisoformat(proposal["expires_at"]) - datetime.fromisoformat(proposal["quoted_at"]) == timedelta(minutes=5)
    assert ctx.db.get(ParkingSession, ctx.session_id).status == "active" and ctx.slot.is_occupied
    assert ctx.db.scalar(select(func.count()).select_from(Payment)) == 0
    assert quote(ctx)["id"] == proposal["id"]


def test_full_online_credit_keeps_car_inside_then_zero_balancing_receipt_prevents_double_revenue(parking_online):
    ctx = parking_online
    settle(ctx, link(ctx, quote(ctx)))
    result = status(ctx)
    assert result["online_paid"] == 10000 and result["balance_due"] == 0
    assert ctx.db.get(ParkingSession, ctx.session_id).status == "active" and ctx.slot.is_occupied
    receipt = ctx.db.scalar(select(Payment))
    assert receipt.source_type == "session_credit" and receipt.method == "transfer"
    assert receipt.collected_by_id is None and receipt.shift_id is None
    completed = checkout(ctx)
    assert completed.parking_fee == 10000 and completed.status == "completed"
    receipts = list(ctx.db.scalars(select(Payment).order_by(Payment.amount.desc())))
    assert [row.amount for row in receipts] == [10000, 0]
    assert receipts[1].source_type == "parking_session" and receipts[1].collected_by_id is None
    start, end = day_bounds(ctx.clock[0].date())
    assert PaymentService.revenue_breakdown(ctx.db, start, end)["parking_revenue"] == 10000
    assert not ctx.db.get(ParkingSlot, ctx.slot.id).is_occupied
    closed = status(ctx)
    assert closed["session_status"] == "completed" and closed["can_quote"] is False


def test_timed_payment_can_cross_a_fee_block_then_cashier_only_collects_remaining(parking_online):
    ctx = parking_online
    ctx.clock[0] = ctx.base + timedelta(minutes=119)
    code = link(ctx, quote(ctx))
    ctx.clock[0] = ctx.base + timedelta(minutes=121)
    settle(ctx, code)
    result = status(ctx)
    assert result["gross_fee"] == 15000 and result["online_paid"] == 10000 and result["balance_due"] == 5000
    completed = checkout(ctx, method="cash")
    assert completed.parking_fee == 15000
    receipts = list(ctx.db.scalars(select(Payment).order_by(Payment.amount.desc())))
    assert [row.amount for row in receipts] == [10000, 5000]
    assert receipts[1].collected_by_id == ctx.users[0].id and receipts[1].method == "cash"
    start, end = day_bounds(ctx.clock[0].date())
    assert PaymentService.revenue_breakdown(ctx.db, start, end)["parking_revenue"] == 15000


def test_timely_webhook_survives_worker_delay_after_quote_expiry(parking_online):
    ctx = parking_online
    proposal = quote(ctx)
    code = link(ctx, proposal)
    ctx.clock[0] = datetime.fromisoformat(proposal["expires_at"]).replace(tzinfo=None) - timedelta(seconds=1)
    identity = receive(ctx, code)
    ctx.clock[0] += timedelta(minutes=6)
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == "processed"
    assert status(ctx)["online_paid"] == 10000


def test_late_webhook_is_review_without_credit_or_automatic_departure(parking_online):
    ctx = parking_online
    proposal = quote(ctx)
    code = link(ctx, proposal)
    ctx.clock[0] = datetime.fromisoformat(proposal["expires_at"]).replace(tzinfo=None) + timedelta(seconds=1)
    identity = receive(ctx, code)
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).reason == "late_or_closed_quote"
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 0
    assert ctx.db.get(ParkingSession, ctx.session_id).status == "active"


def test_quote_without_link_can_expire_and_ui_can_create_a_new_quote(parking_online):
    ctx = parking_online
    first = quote(ctx)
    assert status(ctx)["can_quote"] is False
    ctx.clock[0] = datetime.fromisoformat(first["expires_at"]).replace(tzinfo=None) + timedelta(seconds=1)
    assert status(ctx)["can_quote"] is True
    second = quote(ctx, "session-quote-0002")
    assert first["id"] != second["id"]
    assert ctx.db.get(SessionFeeQuote, first["id"]).status == "expired"


def test_existing_checkout_quote_is_invalidated_when_online_money_arrives(parking_online):
    ctx = parking_online
    prior = CheckoutService(ctx.db).quote(ctx.session_id, ctx.users[0].id)
    settle(ctx, link(ctx, quote(ctx)))
    with pytest.raises(HTTPException) as error:
        checkout(ctx, method="cash", prior=prior)
    assert error.value.status_code == 409
    assert ctx.db.get(ParkingSession, ctx.session_id).status == "active"
    assert ctx.db.scalar(select(func.count()).select_from(Payment)) == 1


def test_two_online_credits_then_checkout_still_collect_each_dong_once(parking_online):
    ctx = parking_online
    settle(ctx, link(ctx, quote(ctx)))
    ctx.clock[0] = ctx.base + timedelta(minutes=130)
    second = quote(ctx, "session-quote-0002")
    assert second["balance_due"] == 5000 and second["online_paid"] == 10000
    settle(ctx, link(ctx, second))
    assert status(ctx)["online_paid"] == 15000
    checkout(ctx)
    assert sorted(ctx.db.scalars(select(Payment.amount))) == [0, 5000, 10000]
    start, end = day_bounds(ctx.clock[0].date())
    assert PaymentService.revenue_breakdown(ctx.db, start, end)["total_revenue"] == 15000


def test_customer_bounds_staff_scope_and_untrusted_amounts(parking_online):
    ctx = parking_online
    proposal = quote(ctx)
    ctx.current["user"] = ctx.users[2]
    assert ctx.client.get(f"/api/v2/me/sessions/{ctx.session_id}/payment-status").status_code == 404
    assert ctx.client.post(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link").status_code == 404
    ctx.current["user"] = ctx.users[0]
    assert ctx.client.get(f"/api/v2/sites/{ctx.site.id}/sessions/{ctx.session_id}/payment-status").status_code == 200
    assert ctx.client.get(f"/api/v2/sites/{ctx.site.id+1}/sessions/{ctx.session_id}/payment-status").status_code == 404
    assert ctx.client.post(f"/api/v2/sites/{ctx.site.id}/sessions/{ctx.session_id}/payment-quote",
        json={"request_id": "forged-amount", "amount": 1}).status_code == 422


def test_pending_link_blocks_duplicate_proposals_even_when_ttl_elapsed(parking_online):
    ctx = parking_online
    first = quote(ctx)
    link(ctx, first)
    ctx.clock[0] = datetime.fromisoformat(first["expires_at"]).replace(tzinfo=None) + timedelta(seconds=1)
    assert status(ctx)["can_quote"] is False
    response = ctx.client.post(f"/api/v2/me/sessions/{ctx.session_id}/payment-quote", json={"request_id": "second-quote-pending"})
    assert response.status_code == 409


def test_disabled_provider_keeps_fee_readable_and_never_creates_a_link(parking_online):
    ctx = parking_online
    ctx.client.app.dependency_overrides[get_online_payment_config] = lambda: OnlinePaymentConfig(_env_file=None, PAYOS_ENABLED=False)
    result = status(ctx)
    assert result["enabled"] is False and result["balance_due"] == 10000 and result["can_quote"] is False
    response = ctx.client.post(f"/api/v2/me/sessions/{ctx.session_id}/payment-quote", json={"request_id": "disabled-fee-quote"})
    assert response.status_code == 503
    assert ctx.provider["calls"] == []


@pytest.mark.parametrize("sql", ["UPDATE session_fee_quotes SET amount=1", "DELETE FROM session_fee_quotes",
    "UPDATE session_fee_credits SET amount=1", "DELETE FROM session_fee_credits",
    "INSERT OR REPLACE INTO session_fee_credits SELECT * FROM session_fee_credits"])
def test_quote_and_credits_are_immutable_in_database(parking_online, sql):
    ctx = parking_online
    settle(ctx, link(ctx, quote(ctx)))
    with pytest.raises(IntegrityError):
        ctx.db.execute(text(sql))
        ctx.db.commit()
    ctx.db.rollback()
    assert status(ctx)["online_paid"] == 10000


def test_timely_webhook_keeps_later_reconcile_retryable_during_provider_outage(parking_online):
    ctx = parking_online
    proposal = quote(ctx)
    code = link(ctx, proposal)
    receive(ctx, code)
    ctx.clock[0] = datetime.fromisoformat(proposal["expires_at"]).replace(tzinfo=None) + timedelta(seconds=1)
    mapping = ctx.db.get(OnlinePaymentLink, code)
    expected = online_payment_service._expectation(mapping)
    ctx.db.commit()
    verified = ctx.fee_gateway.get_link(expected)
    later = online_payment_service._record_snapshot(ctx.db, mapping, verified, ctx.config)[0]
    ctx.db.commit()

    def offline(request):
        assert not ctx.db.in_transaction()
        raise httpx.ReadTimeout("temporary offline failure", request=request)

    with httpx.Client(transport=httpx.MockTransport(offline), trust_env=False) as transport:
        online_payment_service.process_inbox(ctx.db, later, ctx.config, PayOSGateway(ctx.config.adapter_settings(), transport))
    assert ctx.db.get(OnlinePaymentProcessing, later).status == "received"
    assert ctx.db.get(SessionFeeQuote, proposal["id"]).status == "pending"
    online_payment_service.process_inbox(ctx.db, later, ctx.config, ctx.fee_gateway)
    assert status(ctx)["online_paid"] == 10000


@pytest.mark.parametrize("paid", [False, True])
def test_online_binding_blocks_cancel_and_correction_but_preserves_lost_ticket(parking_online, paid):
    from services.session_exception_service import SessionExceptionService
    ctx = parking_online
    code = link(ctx, quote(ctx))
    if paid:
        settle(ctx, code)
    result = SessionExceptionService(ctx.db).detail(ctx.users[0], ctx.site.id, ctx.session_id)
    assert result["eligibility"]["cancel"]["allowed"] is False
    assert "online" in result["eligibility"]["cancel"]["reason"]
    assert result["eligibility"]["correct_plate"]["allowed"] is False
    assert result["eligibility"]["lost_ticket"]["allowed"] is True


def test_order_codes_are_random_safe_integers_and_collision_is_retried_before_http(parking_online, monkeypatch):
    ctx = parking_online
    candidates = iter([73123456, 73123456, 73123457])
    monkeypatch.setattr(online_payment_service.secrets, "randbelow", lambda bound: next(candidates))
    first = link(ctx, quote(ctx))
    assert first == 73123457 and first != 1
    settle(ctx, first)
    ctx.clock[0] = ctx.base + timedelta(minutes=130)
    second_quote = quote(ctx, "collision-next-quote")
    second = link(ctx, second_quote)
    assert second == 73123458
    assert sum(method == "POST" for method, _ in ctx.provider["calls"]) == 2
    assert link(ctx, second_quote) == second
    assert sum(method == "POST" for method, _ in ctx.provider["calls"]) == 2


def test_payment_after_cash_departure_goes_to_review_without_second_receipt(parking_online):
    ctx = parking_online
    code = link(ctx, quote(ctx))
    checkout(ctx, method="cash")
    identity = receive(ctx, code)
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).reason == "session_no_longer_active"
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 0
    assert list(ctx.db.scalars(select(Payment.amount))) == [10000]


def test_cancel_unmapped_quote_and_immediate_provider_cancel_leave_car_inside(parking_online):
    ctx = parking_online
    first = quote(ctx)
    response = ctx.client.post(f"/api/v2/session-fee-quotes/{first['id']}/payment-link/cancel", json={"reason": "Change payment choice"})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "cancelled" and ctx.provider["calls"] == []
    second = quote(ctx, "cancel-second-quote")
    link(ctx, second)
    response = ctx.client.post(f"/api/v2/session-fee-quotes/{second['id']}/payment-link/cancel", json={"reason": "Pay at exit instead"})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "cancelled"
    assert ctx.provider["calls"][-1][1].endswith("/cancel")
    assert ctx.db.get(ParkingSession, ctx.session_id).status == "active" and ctx.slot.is_occupied
    assert status(ctx)["can_quote"] is True


@pytest.mark.parametrize("provider_status", ["EXPIRED", "CANCELLED"])
def test_terminal_provider_projection_cannot_unblock_accepted_unprocessed_money(parking_online, provider_status):
    ctx = parking_online
    proposal = quote(ctx)
    code = link(ctx, proposal)
    identity = receive(ctx, code)
    ctx.provider["links"][code].update(paid=False, status=provider_status)
    ctx.clock[0] += timedelta(seconds=11)
    response = ctx.client.post(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link/refresh")
    assert response.status_code == 200, response.text
    assert ctx.db.get(SessionFeeQuote, proposal["id"]).status in {"expired", "cancelled"}
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == "received"
    assert status(ctx)["can_quote"] is False
    response = ctx.client.post(f"/api/v2/me/sessions/{ctx.session_id}/payment-quote", json={"request_id": "unresolved-old-money"})
    assert response.status_code == 409
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == "review"
    assert status(ctx)["can_quote"] is False
    assert ctx.db.scalar(select(func.count()).select_from(Payment)) == 0


def test_cancelled_session_has_no_accruing_fee_or_phantom_debt(exception_env):
    from expansion.session_payment_service import payment_status
    ctx = exception_env
    response = ctx.client.post(ctx.base + "/cancel", json={"request_id": "cancelled-no-online-debt", "reason": "Wrong admission"})
    assert response.status_code == 200, response.text
    result = payment_status(ctx.db, ctx.manager, ctx.session.id, OnlinePaymentConfig(_env_file=None, PAYOS_ENABLED=False), site_id=ctx.site.id)
    assert result["session_status"] == "cancelled"
    assert result["gross_fee"] == result["online_paid"] == result["balance_due"] == 0
    assert result["billing_basis"] is None and result["can_quote"] is False


def test_online_credit_cannot_refund_while_active_but_closed_refund_keeps_gross_credit(parking_online):
    ctx = parking_online
    settle(ctx, link(ctx, quote(ctx)))
    receipt_id = ctx.db.scalar(select(Payment.id))
    kwargs = dict(amount=5000, method="transfer", reason="Approved offline refund", idempotency_key="session-credit-refund-1")
    with pytest.raises(HTTPException) as error:
        PaymentService.refund(ctx.db, receipt_id, ctx.users[0], **kwargs)
    assert error.value.status_code == 409
    ctx.db.rollback()
    checkout(ctx)
    refund = PaymentService.refund(ctx.db, receipt_id, ctx.users[0], **kwargs)
    ctx.db.commit()
    assert refund.amount == 5000
    assert status(ctx)["online_paid"] == 10000
    start, end = day_bounds(ctx.clock[0].date())
    assert PaymentService.revenue_breakdown(ctx.db, start, end)["total_revenue"] == 5000


@pytest.mark.parametrize("operation", ["create", "refresh", "cancel"])
@pytest.mark.parametrize("network_error", [False, True])
def test_revoke_customer_during_http_retains_mapping_but_never_returns_qr(parking_online, monkeypatch, operation, network_error):
    from expansion.portal_models import PortalAccountLink
    from expansion.payos_gateway import PayOSGatewayError
    ctx = parking_online
    proposal = quote(ctx)
    endpoint = f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link"
    if operation != "create":
        link(ctx, proposal)
        ctx.clock[0] += timedelta(seconds=11)
        endpoint += "/" + operation
    method = {"create": "create_link", "refresh": "get_link", "cancel": "cancel_link"}[operation]
    original = getattr(ctx.fee_gateway, method)

    def revoke(request, **kwargs):
        result = original(request, **kwargs)
        ctx.db.execute(delete(PortalAccountLink))
        ctx.db.commit()
        if network_error:
            raise PayOSGatewayError(outcome_unknown=True)
        return result

    monkeypatch.setattr(ctx.fee_gateway, method, revoke)
    response = ctx.client.post(endpoint, json={"reason": "Change payment choice"} if operation == "cancel" else None)
    assert response.status_code == 404, response.text
    assert ctx.db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1
    assert ctx.db.scalar(select(func.count()).select_from(Payment)) == 0
    assert ctx.client.get(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link").status_code == 404


@pytest.mark.parametrize("closed_source", ["session", "site"])
def test_closed_source_during_create_hides_payment_instructions_and_retains_reconciliation(parking_online, monkeypatch, closed_source):
    ctx = parking_online
    proposal = quote(ctx)
    endpoint = f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link"
    original = ctx.fee_gateway.create_link

    def close(request):
        result = original(request)
        if closed_source == "session":
            checkout(ctx, method="cash")
        else:
            ctx.site.is_active = False
            ctx.db.commit()
        return result

    monkeypatch.setattr(ctx.fee_gateway, "create_link", close)
    response = ctx.client.post(endpoint)
    assert response.status_code == 200, response.text
    for view in [response.json(), ctx.client.get(endpoint).json()]:
        assert view["qr_code"] is None and view["qr_svg"] is None and view["checkout_url"] is None
        assert view["can_create"] is False
        assert view["can_refresh"] is True
    assert ctx.db.scalar(select(func.count()).select_from(OnlinePaymentLink)) == 1
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 0
