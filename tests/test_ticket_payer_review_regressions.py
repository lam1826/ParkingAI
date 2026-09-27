"""Ticket payer privacy and delayed signed evidence, isolated DB/fake provider."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from expansion import online_payment_service
from expansion.online_payment_models import OnlinePaymentInbox, OnlinePaymentProcessing
from expansion.session_payment_models import SessionFeeCredit
from expansion.simplified_customer_models import SessionPaymentAccess, SessionTicketCredential
from expansion.simplified_customer_router import router as customer_router
from services.ticket_service import get_ticket
from test_session_online_payments import (
    parking_online, online, no_external_payment_configuration, portal, quote, link, receive,  # noqa: F401
)


def ticket_payer(ctx):
    ctx.client.app.include_router(customer_router, prefix='/api/v2')
    proof = get_ticket(ctx.db, ctx.session_id)['payment_access_code']
    ctx.current['user'] = ctx.users[2]
    response = ctx.client.post('/api/v2/me/fee-lookup', json={
        'site_id': ctx.site.id, 'license_plate': '30A12345',
        'vehicle_type_id': ctx.portal[4].id, 'ticket_proof': proof})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('creator', ['owner', 'staff'])
def test_ticket_status_does_not_offer_someone_elses_quote(parking_online, creator):
    ctx = parking_online
    if creator == 'owner':
        proposal = quote(ctx)
    else:
        ctx.current['user'] = ctx.users[0]
        response = ctx.client.post(f'/api/v2/sites/{ctx.site.id}/sessions/{ctx.session_id}/payment-quote',
                                  json={'request_id': 'staff-review-quote-01'})
        assert response.status_code == 200, response.text
        proposal = response.json()
    ticket_payer(ctx)
    response = ctx.client.get(f'/api/v2/me/sessions/{ctx.session_id}/payment-status')
    assert response.status_code == 200
    assert response.json()['latest_quote'] is None
    assert response.json()['can_quote'] is False
    assert 'nhân viên' in response.json()['message']
    assert ctx.client.get(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link").status_code == 404
    assert ctx.client.post(f'/api/v2/me/sessions/{ctx.session_id}/payment-quote',
                           json={'request_id': 'no-duplicate-review-01'}).status_code == 409


@pytest.mark.parametrize('delay', ['after_24_hours', 'crosses_access_expiry'])
def test_timely_ticket_payment_survives_natural_access_expiry(parking_online, delay):
    ctx = parking_online
    ticket_payer(ctx)
    if delay == 'crosses_access_expiry':
        ctx.clock[0] += timedelta(hours=23, minutes=59)
    proposal = quote(ctx)
    code = link(ctx, proposal)
    ctx.clock[0] += timedelta(seconds=30)
    identity = receive(ctx, code)
    ctx.clock[0] += timedelta(hours=25) if delay == 'after_24_hours' else timedelta(seconds=60)
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == 'processed'
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 1
    assert ctx.client.get(f'/api/v2/me/sessions/{ctx.session_id}/payment-status').status_code == 404
    # A webhook replay must not credit it twice.
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 1


@pytest.mark.parametrize('change', ['revoked', 'rotated', 'disabled_user', 'retroactive_access', 'expired_at_receipt'])
def test_delayed_payment_still_rejects_revoked_or_retroactive_access(parking_online, change):
    ctx = parking_online
    ticket_payer(ctx)
    if change == 'expired_at_receipt':
        ctx.clock[0] += timedelta(hours=23, minutes=59)
    code = link(ctx, quote(ctx))
    if change == 'expired_at_receipt':
        ctx.clock[0] += timedelta(seconds=60)  # Access expired, proposal still valid.
    identity = receive(ctx, code)
    access = ctx.db.scalar(select(SessionPaymentAccess).where(SessionPaymentAccess.session_id == ctx.session_id))
    if change == 'revoked':
        access.revoked_at = ctx.clock[0]
    elif change == 'rotated':
        ctx.db.get(SessionTicketCredential, ctx.session_id).version = 'replaced-proof-version'
    elif change == 'disabled_user':
        ctx.users[2].is_active = False
    elif change == 'retroactive_access':
        access.created_at = ctx.db.get(OnlinePaymentInbox, identity).received_at + timedelta(seconds=1)
    ctx.db.commit()
    ctx.clock[0] += timedelta(hours=25)
    online_payment_service.process_inbox(ctx.db, identity, ctx.config, ctx.fee_gateway)
    assert ctx.db.get(OnlinePaymentProcessing, identity).status == 'review'
    assert ctx.db.get(OnlinePaymentProcessing, identity).reason == 'session_payment_access_revoked'
    assert ctx.db.scalar(select(func.count()).select_from(SessionFeeCredit)) == 0
