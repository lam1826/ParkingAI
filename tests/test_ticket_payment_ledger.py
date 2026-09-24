"""Ticket payer sees only their real-flow mocked-provider credit receipts."""
from datetime import timedelta

from sqlalchemy import select

from expansion.online_payment_worker import run_online_payment_maintenance
from expansion.online_payment_models import OnlinePaymentProcessing
from expansion.portal_models import PortalAccountLink, PortalSessionGrant
from expansion.simplified_customer_router import router
from expansion.ticket_payment_access import revoke_ticket_payment_access
from models.parking_session import ParkingSession
from models.payment import Payment
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService
from services.parking_service import ParkingService
from services.ticket_service import get_ticket
from test_online_payments import online, no_external_payment_configuration  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_session_payment_acceptance import fee_acceptance, verified_payment  # noqa: F401


def unlinked_payer(fixture):
    ctx, instant, slot, rate, mappings, gateway = fixture
    ctx.client.app.include_router(router, prefix='/api/v2')
    identity = ParkingService(ctx.db).check_in('51A-446.67', rate.vehicle_type_id, ctx.users[0].id,
        parking_slot_id=slot.id)['session_id']
    proof = get_ticket(ctx.db, identity)['payment_access_code']
    instant['at'] += timedelta(seconds=1)
    ctx.current['user'] = ctx.users[2]
    assert ctx.db.scalar(select(PortalAccountLink).where(PortalAccountLink.user_id == ctx.users[2].id)) is None
    response = ctx.client.post('/api/v2/me/fee-lookup', json={'site_id': ctx.site.id,
        'license_plate': '51a44667', 'vehicle_type_id': rate.vehicle_type_id, 'ticket_proof': proof})
    assert response.status_code == 200, response.text
    assert ctx.db.get(PortalSessionGrant, identity) is None
    return identity


def test_unlinked_ticket_payer_credit_receipt_survives_exit_without_cashier_history(fee_acceptance):
    ctx, instant, slot, rate, mappings, gateway = fee_acceptance
    identity = unlinked_payer(fee_acceptance)
    verified_payment(ctx, identity, mappings)
    run_online_payment_maintenance(ctx.db, ctx.config, gateway)
    status = ctx.client.get(f'/api/v2/me/sessions/{identity}/payment-status')
    assert status.status_code == 200, status.text
    assert status.json()['online_paid'] == 5000
    quote = CheckoutService(ctx.db).quote(identity, ctx.users[0].id)
    assert quote['balance_due'] == 0
    CheckoutService(ctx.db).confirm(CheckoutConfirmation(quote_token=quote['quote_token'], payment_confirmed=True,
        payment_method=None), ctx.users[0].id, session_id=identity)
    assert ctx.client.get(f'/api/v2/me/sessions/{identity}/payment-status').status_code == 404
    instant['at'] += timedelta(days=2)
    response = ctx.client.get('/api/v2/me/receipts')
    assert response.status_code == 200, response.text
    receipts = response.json()['items']
    assert len(receipts) == 1 and receipts[0]['source_type'] == 'session_credit' and receipts[0]['amount'] == 5000
    own_pdf = f"/api/v2/me/receipts/{receipts[0]['id']}/pdf"
    assert ctx.client.get(own_pdf).content.startswith(b'%PDF')
    balancing = ctx.db.scalar(select(Payment).where(Payment.source_type == 'parking_session', Payment.source_id == identity))
    assert ctx.client.get(f'/api/v2/me/receipts/{balancing.id}/pdf').status_code == 404
    ctx.current['user'] = ctx.users[1]
    assert ctx.client.get(own_pdf).status_code == 404
    assert ctx.db.get(ParkingSession, identity).parking_fee == 5000


def test_revoked_ticket_before_worker_leaves_verified_money_for_review(fee_acceptance):
    ctx, instant, slot, rate, mappings, gateway = fee_acceptance
    identity = unlinked_payer(fee_acceptance)
    verified_payment(ctx, identity, mappings)
    revoke_ticket_payment_access(ctx.db, identity)
    ctx.db.commit()
    run_online_payment_maintenance(ctx.db, ctx.config, gateway)
    processing = ctx.db.scalar(select(OnlinePaymentProcessing))
    assert processing.status == 'review' and processing.reason == 'session_payment_access_revoked'
    assert ctx.db.scalar(select(Payment.id).where(Payment.source_type == 'session_credit')) is None
    assert ctx.db.get(ParkingSession, identity).status == 'active'
