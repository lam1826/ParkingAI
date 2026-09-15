"""Independent fee acceptance through actual APIs and an offline signed transport."""
from datetime import datetime, timedelta
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import core.clock as clock
from expansion.online_payment_models import OnlinePaymentLink
from expansion.online_payment_router import get_payos_gateway
from expansion.online_payment_worker import run_online_payment_maintenance
from expansion.payos_gateway import PayOSGateway
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


@pytest.fixture
def fee_acceptance(online, monkeypatch):
    ctx = online
    ctx.client.app.include_router(router, prefix="/api/v2")
    # Ownership is established by the upstream fixture before admission. Keep
    # entry after that event even when the suite runs later in the day.
    instant = {"at": clock.business_now() + timedelta(seconds=1)}

    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            aware = instant["at"].replace(tzinfo=clock.BUSINESS_TZ)
            return aware.astimezone(tz) if tz else aware.astimezone().replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", FrozenClock)
    kind = ctx.portal[4]
    zone = Zone(name="Independent fee acceptance", capacity=1, site_id=ctx.site.id, is_active=True)
    ctx.db.add(zone); ctx.db.flush()
    slot = ParkingSlot(slot_name="FEE-1", zone_id=zone.id, vehicle_type_id=kind.id, is_active=True, is_occupied=False)
    rate = PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=5000,
        effective_date=instant["at"].date(), is_active=True)
    ctx.db.add_all([slot, rate]); ctx.db.commit()
    mappings = {}

    def transport(request):
        assert not ctx.db.in_transaction()
        if request.method == "GET":
            code = int(request.url.path.rsplit("/", 1)[-1])
            saved = mappings[code]
            entries = [transaction(amount=saved["amount"], reference=saved["reference"])] if saved.get("reference") else []
            return httpx.Response(200, json=signed(link_data(id=saved["id"], orderCode=code,
                amount=saved["amount"], amountPaid=saved["amount"] if entries else 0,
                amountRemaining=0 if entries else saved["amount"], transactions=entries, status="PAID" if entries else "PENDING")))
        assert request.method == "POST" and request.url.path == "/v2/payment-requests"
        body = json.loads(request.content)
        with Session(ctx.db.get_bind()) as independent:
            persisted = independent.get(OnlinePaymentLink, body["orderCode"])
            assert persisted is not None and persisted.session_quote_id is not None
        provider_id = uuid4().hex
        mappings[body["orderCode"]] = {"id": provider_id, "amount": body["amount"]}
        return httpx.Response(200, json=signed(created_data(paymentLinkId=provider_id,
            orderCode=body["orderCode"], amount=body["amount"], description=body["description"], expiredAt=body["expiredAt"],
            checkoutUrl="https://pay.payos.vn/web/" + provider_id)))

    with httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as transport_client:
        gateway = PayOSGateway(ctx.config.adapter_settings(), transport_client)
        ctx.client.app.dependency_overrides[get_payos_gateway] = lambda: gateway
        yield ctx, instant, slot, rate, mappings, gateway


def verified_payment(ctx, session_id, mappings):
    response = ctx.client.post(f"/api/v2/me/sessions/{session_id}/payment-quote", json={"request_id": uuid4().hex})
    assert response.status_code == 200, response.text
    quote = response.json()
    path = f"/api/v2/session-fee-quotes/{quote['id']}/payment-link"
    response = ctx.client.post(path)
    assert response.status_code == 200, response.text
    assert response.json()["quote_id"] == quote["id"] and response.json()["order_id"] is None
    link = ctx.db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.session_quote_id == quote["id"]))
    code, provider_id, amount = link.id, mappings[link.id]["id"], link.amount
    ctx.db.rollback()
    reference = "OFFLINE-" + uuid4().hex
    mappings[code]["reference"] = reference
    payload = signed({"orderCode": code, "paymentLinkId": provider_id, "amount": amount,
        "currency": "VND", "accountNumber": ACCOUNT, "reference": reference,
        "description": "INDEPENDENT FEE TEST", "transactionDateTime": "2026-09-15 10:00:00",
        "code": "00", "desc": "Success"}, success=True)
    response = ctx.client.post("/api/v2/payments/payos/webhook", content=json.dumps(payload).encode())
    assert response.status_code == 200, response.text
    return quote, payload


@pytest.mark.parametrize("ticket_type,block", [("HOURLY", timedelta(hours=1)), ("DAILY", timedelta(days=1))])
def test_two_online_payments_across_block_boundary_keep_gross_and_collect_nothing_twice(fee_acceptance, ticket_type, block):
    ctx, instant, slot, rate, mappings, gateway = fee_acceptance
    rate.ticket_type = ticket_type; ctx.db.commit()
    vehicle = ctx.db.get(Vehicle, ctx.body["vehicle_id"])
    entry = instant["at"]
    admission = ParkingService(ctx.db).check_in(vehicle.license_plate, vehicle.vehicle_type_id,
        ctx.users[0].id, parking_slot_id=slot.id)
    identity = admission["session_id"]
    instant["at"] = entry + timedelta(seconds=1)
    first, first_event = verified_payment(ctx, identity, mappings)
    assert first["balance_due"] == 5000
    run_online_payment_maintenance(ctx.db, ctx.config, gateway)
    status = ctx.client.get(f"/api/v2/me/sessions/{identity}/payment-status").json()
    assert (status["gross_fee"], status["online_paid"], status["balance_due"]) == (5000, 5000, 0)
    ctx.db.refresh(slot); assert slot.is_occupied is True
    instant["at"] = entry + block
    checkout = CheckoutService(ctx.db).quote(identity, ctx.users[0].id)
    assert checkout["balance_due"] == 0
    instant["at"] += timedelta(microseconds=1)
    second, _event = verified_payment(ctx, identity, mappings)
    assert second["gross_fee"] == 10000 and second["online_paid"] == 5000 and second["balance_due"] == 5000
    assert second["id"] != first["id"] and len(mappings) == 2
    run_online_payment_maintenance(ctx.db, ctx.config, gateway)
    repeated = ctx.client.post("/api/v2/payments/payos/webhook", content=json.dumps(first_event).encode())
    assert repeated.status_code == 200
    run_online_payment_maintenance(ctx.db, ctx.config, gateway)
    quote = CheckoutService(ctx.db).quote(identity, ctx.users[0].id)
    assert (quote["parking_fee"], quote["online_paid"], quote["balance_due"]) == (10000, 10000, 0)
    confirmation = CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True, payment_method=None)
    done = CheckoutService(ctx.db).confirm(confirmation, ctx.users[0].id, session_id=identity)
    assert done.parking_fee == 10000 and done.status == "completed"
    assert CheckoutService(ctx.db).confirm(confirmation, ctx.users[0].id, session_id=identity).id == identity
    receipts = ctx.db.scalars(select(Payment).where(Payment.kind == "receipt")).all()
    assert sorted((row.source_type, row.amount) for row in receipts) == [
        ("parking_session", 0), ("session_credit", 5000), ("session_credit", 5000)]
    assert all(row.collected_by_id is None and row.shift_id is None for row in receipts)
    ctx.db.refresh(slot); assert slot.is_occupied is False
    revenue = PaymentService.revenue_breakdown(ctx.db, entry - timedelta(days=1), instant["at"] + timedelta(days=1))
    assert revenue["parking_revenue"] == 10000 and revenue["total_revenue"] == 10000
    assert ctx.db.get(ParkingSession, identity).parking_fee == 10000
    own_receipts = ctx.client.get("/api/v2/me/receipts").json()["items"]
    assert len(own_receipts) == 3 and sum(row["amount"] for row in own_receipts) == 10000
    for receipt in own_receipts:
        pdf = ctx.client.get(f"/api/v2/me/receipts/{receipt['id']}/pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), pdf.text[:200]
