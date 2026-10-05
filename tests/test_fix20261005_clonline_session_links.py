"""CL-ONLINE fix 05/10 (#49): a session-fee link that payOS never created stops blocking after expiry.

Offline only: the provider is an httpx MockTransport that never creates the order code.
"""
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from expansion.online_payment_models import OnlinePaymentLink
from expansion.online_payment_worker import run_online_payment_maintenance
from expansion.session_payment_models import SessionFeeQuote

from test_online_payments import online, no_external_payment_configuration  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_session_online_payments import parking_online, status, quote  # noqa: F401


def _never_created(calls):
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST" and not request.url.path.endswith("/cancel"):
            raise httpx.ConnectError("offline connect failure", request=request)
        return httpx.Response(404, json={"code": "101", "desc": "order not found", "data": None})
    return handler


def _stuck_quote(ctx):
    calls = []
    ctx.fee_gateway.client = httpx.Client(transport=httpx.MockTransport(_never_created(calls)), trust_env=False)
    proposal = quote(ctx)
    created = ctx.client.post(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link")
    assert created.status_code == 200 and created.json()["state"] == "unknown"
    return proposal, datetime.fromisoformat(proposal["expires_at"]).replace(tzinfo=None)


def test_never_created_link_does_not_block_a_new_quote_after_expiry(parking_online):
    ctx = parking_online
    proposal, expires = _stuck_quote(ctx)
    assert status(ctx)["can_quote"] is False  # still inside the quote window
    ctx.clock[0] = expires + timedelta(minutes=6)
    assert status(ctx)["can_quote"] is True
    again = ctx.client.post(f"/api/v2/me/sessions/{ctx.session_id}/payment-quote", json={"request_id": "clonline-after-stuck"})
    assert again.status_code == 200, again.text
    ctx.db.expire_all()
    assert ctx.db.get(SessionFeeQuote, proposal["id"]).status == "expired"
    old_link = ctx.db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.session_quote_id == proposal["id"]))
    assert old_link.state == "expired"


def test_worker_closes_never_created_link_after_expiry(parking_online):
    ctx = parking_online
    proposal, expires = _stuck_quote(ctx)
    ctx.clock[0] = expires + timedelta(minutes=6)
    run_online_payment_maintenance(ctx.db, ctx.config, ctx.fee_gateway)
    ctx.db.expire_all()
    link = ctx.db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.session_quote_id == proposal["id"]))
    assert link.state == "expired" and link.payment_link_id is None
    assert ctx.db.get(SessionFeeQuote, proposal["id"]).status == "expired"
    assert status(ctx)["can_quote"] is True


def test_never_created_link_still_blocks_inside_the_grace_window(parking_online):
    ctx = parking_online
    proposal, expires = _stuck_quote(ctx)
    ctx.clock[0] = expires + timedelta(minutes=1)
    run_online_payment_maintenance(ctx.db, ctx.config, ctx.fee_gateway)
    ctx.db.expire_all()
    link = ctx.db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.session_quote_id == proposal["id"]))
    assert link.state == "unknown"
    assert status(ctx)["can_quote"] is False
