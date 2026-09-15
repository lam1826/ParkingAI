"""Independent regressions: payment instructions follow current source state."""
import pytest
from sqlalchemy import select

from expansion.online_payment_models import OnlinePaymentLink
from test_session_online_payments import (
    parking_online, online, no_external_payment_configuration, portal,
    quote, link, checkout,
)


@pytest.mark.parametrize("operation", ["completed", "site_closed"])
def test_current_source_rejects_new_payment_instructions(parking_online, operation):
    ctx = parking_online
    proposal = quote(ctx)
    link(ctx, proposal)
    if operation == "completed":
        checkout(ctx, method="cash")
    else:
        ctx.site.is_active = False
        ctx.db.commit()
    response = ctx.client.get(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link")
    if response.status_code == 200:
        view = response.json()
        assert not view["qr_svg"], "Current source must suppress QR instructions"
        assert not view["checkout_url"], "Current source must suppress provider link"
        assert not view["can_create"]
    else:
        assert response.status_code in {403, 404, 409}


def test_checkout_during_create_keeps_provider_evidence_without_returning_qr(parking_online, monkeypatch):
    ctx = parking_online
    proposal = quote(ctx)
    original = ctx.fee_gateway.create_link

    def complete_then_return(request):
        checkout(ctx, method="cash")
        ctx.db.rollback()  # Close the completed object's incidental refresh read.
        return original(request)

    monkeypatch.setattr(ctx.fee_gateway, "create_link", complete_then_return)
    response = ctx.client.post(f"/api/v2/session-fee-quotes/{proposal['id']}/payment-link")
    persisted = ctx.db.scalar(select(OnlinePaymentLink).where(OnlinePaymentLink.session_quote_id == proposal["id"]))
    assert persisted is not None
    if response.status_code == 200:
        assert not response.json()["qr_svg"], "Completed during provider HTTP must suppress QR"
        assert not response.json()["checkout_url"]
    else:
        assert response.status_code in {403, 404, 409}
