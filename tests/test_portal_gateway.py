import pytest
from fastapi import HTTPException

from expansion.gateway import DemoGateway, PortalSettings


def test_demo_is_disabled_by_default_and_never_creates_a_bank_payment():
    gateway = DemoGateway(PortalSettings(_env_file=None, DEMO_PAYMENTS_ENABLED=False))
    with pytest.raises(HTTPException) as caught:
        gateway.issue("order-1")
    assert caught.value.status_code == 503


def test_demo_nonce_is_random_bound_to_order_and_payload_is_explicitly_demo():
    gateway = DemoGateway(PortalSettings(_env_file=None, DEMO_PAYMENTS_ENABLED=True))
    token, payload = gateway.issue("order-1")
    other, _ = gateway.issue("order-1")
    assert token != other and len(token) >= 40
    assert payload.startswith("PARKINGAI-DEMO:")
    assert gateway.verify(token, token)
    assert not gateway.verify(token, other)
    assert not gateway.verify(token, "")
