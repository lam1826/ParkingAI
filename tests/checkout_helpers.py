"""Explicit opt-in confirmation setup for legitimate checkout regression tests.

Never wrap TestClient or inject payloads into arbitrary requests: security tests
must continue to send their actual missing/invalid bodies unchanged.
"""
from schemas.checkout import CheckoutConfirmation
from services.checkout_service import CheckoutService


def quote_confirmation(client, headers, session_id, *, payment_method="cash"):
    response = client.get(f"/api/v1/parking-sessions/{session_id}/checkout-quote", headers=headers)
    assert response.status_code == 200, response.text
    quote = response.json()
    return {
        "quote_token": quote["quote_token"], "payment_confirmed": True,
        "payment_method": payment_method if quote["parking_fee"] > 0 else None,
    }


def service_confirmation(db, session_id, actor_id, *, payment_method="cash"):
    quote = CheckoutService(db).quote(session_id, actor_id)
    return CheckoutConfirmation(
        quote_token=quote["quote_token"], payment_confirmed=True,
        payment_method=payment_method if quote["parking_fee"] > 0 else None,
    )
