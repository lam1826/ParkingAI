"""Offline contract tests: all HTTP uses MockTransport and public/fake keys.

Known webhook vector is published at:
https://payos.vn/docs/tich-hop-webhook/kiem-tra-du-lieu-voi-signature/
Additional literal vectors use the canonical strings defined in the payOS 1.1.0
SDK source: src/payos/_crypto/provider.py. No application signing helper is used
as the expected-value oracle.
"""
import copy
import hashlib
import hmac
import json

import httpx
import pytest
from pydantic import ValidationError

from expansion.payos_gateway import (
    API_BASE_URL, CreateLinkRequest, PaymentExpectation, PayOSDisabledError,
    PayOSGateway, PayOSInputError, PayOSMismatchError, PayOSProtocolError,
    PayOSProviderError, PayOSSettings, PayOSSignatureError, PayOSTransportError,
)


# A published documentation example, not a credential for any configured account.
PUBLIC_EXAMPLE_CHECKSUM = "1a54716c8f0efb2744fb28b6e38b25da7f67a925d98bc1c18bd8faaecadd7675"
PUBLIC_EXAMPLE_SIGNATURE = "412e915d2871504ed31be63c8f62a149a4410d34c4c42affc9006ef9917eaa03"
LINK_ID = "124c33293c43417ab7879e14c8d9eb18"
ACCOUNT = "12345678"


def configured(**changes):
    values = {"PAYOS_ENABLED": True, "PAYOS_CLIENT_ID": "FAKE_CLIENT_ID",
        "PAYOS_API_KEY": "FAKE_API_KEY", "PAYOS_CHECKSUM_KEY": PUBLIC_EXAMPLE_CHECKSUM,
        "PAYOS_RECEIVER_ACCOUNT_NUMBER": ACCOUNT}
    return PayOSSettings(**(values | changes))


def expectation(**changes):
    return PaymentExpectation(**({"order_code": 123, "amount": 3000, "payment_link_id": LINK_ID} | changes))


def request_data(**changes):
    return CreateLinkRequest(**({"order_code": 123, "amount": 3000, "description": "PARK123",
        "return_url": "https://parking.example/return?order=123&view=qr",
        "cancel_url": "https://parking.example/cancel?order=123&view=qr", "expires_at": 1_790_000_000} | changes))


def webhook_data():
    return {"orderCode": 123, "amount": 3000, "description": "VQRIO123", "accountNumber": ACCOUNT,
        "reference": "TF230204212323", "transactionDateTime": "2023-02-04 18:25:00", "currency": "VND",
        "paymentLinkId": LINK_ID, "code": "00", "desc": "Thành công", "counterAccountBankId": "",
        "counterAccountBankName": "", "counterAccountName": "", "counterAccountNumber": "",
        "virtualAccountName": "", "virtualAccountNumber": ""}


def raw_webhook():
    return json.dumps({"code": "00", "desc": "success", "success": True, "data": webhook_data(),
        "signature": PUBLIC_EXAMPLE_SIGNATURE}, ensure_ascii=False).encode("utf-8")


def signed(data, **envelope_changes):
    """Independent fixture signer following provider source; literal vectors anchor it."""
    fields = []
    for key, value in sorted(data.items()):
        if isinstance(value, list):
            value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        elif value is None or value in ("null", "undefined"):
            value = ""
        elif type(value) is bool:
            value = "true" if value else "false"
        fields.append(f"{key}={value}")
    signature = hmac.new(PUBLIC_EXAMPLE_CHECKSUM.encode(), "&".join(fields).encode(), hashlib.sha256).hexdigest()
    return {"code": "00", "desc": "success", "data": data, "signature": signature, **envelope_changes}


def transaction(**changes):
    return {"reference": "FAKE-TX-123", "amount": 3000, "accountNumber": ACCOUNT,
        "description": "PARK123", "transactionDateTime": "2026-09-15 10:30:00", **changes}


def link_data(**changes):
    return {"id": LINK_ID, "orderCode": 123, "amount": 3000, "amountPaid": 3000,
        "amountRemaining": 0, "status": "PAID", "createdAt": "2026-09-15T03:20:00.000Z",
        "transactions": [transaction()], **changes}


def created_data(**changes):
    return {"paymentLinkId": LINK_ID, "orderCode": 123, "amount": 3000, "currency": "VND",
        "accountNumber": ACCOUNT, "accountName": "FAKE RECEIVER", "bin": "970422", "description": "PARK123",
        "status": "PENDING", "checkoutUrl": f"https://pay.payos.vn/web/{LINK_ID}",
        "qrCode": "FAKE_QR_PAYLOAD", "expiredAt": 1_790_000_000, **changes}


@pytest.fixture
def make_gateway():
    clients = []

    def make(handler=None, *, settings=None):
        def no_http(_request):
            pytest.fail("Pure verification/configuration must not perform HTTP")
        client = httpx.Client(transport=httpx.MockTransport(handler or no_http), trust_env=False)
        clients.append(client)
        return PayOSGateway(settings or configured(), client)

    yield make
    for client in clients:
        client.close()


def test_configuration_never_reads_environment_or_exposes_secrets(monkeypatch, make_gateway):
    monkeypatch.setenv("PAYOS_ENABLED", "true")
    monkeypatch.setenv("PAYOS_API_KEY", "UNRELATED_ENV_SECRET")
    settings = PayOSSettings()
    assert settings.PAYOS_ENABLED is False and settings.PAYOS_API_KEY is None
    configured_settings = configured()
    for secret in ("FAKE_CLIENT_ID", "FAKE_API_KEY", PUBLIC_EXAMPLE_CHECKSUM, ACCOUNT):
        assert secret not in repr(configured_settings)
        assert secret not in configured_settings.model_dump_json()
    gateway = make_gateway(settings=settings)
    for action in (lambda: gateway.create_link(request_data()), lambda: gateway.get_link(expectation()),
            lambda: gateway.cancel_link(expectation()), lambda: gateway.verify_webhook(raw_webhook())):
        with pytest.raises(PayOSDisabledError) as error:
            action()
        assert not error.value.outcome_unknown


@pytest.mark.parametrize("changes", [
    {"PAYOS_CLIENT_ID": None}, {"PAYOS_API_KEY": ""}, {"PAYOS_CHECKSUM_KEY": "  "},
    {"PAYOS_RECEIVER_ACCOUNT_NUMBER": None}, {"PAYOS_RECEIVER_ACCOUNT_NUMBER": "not-an-account"},
    {"PAYOS_API_KEY": "FAKE\r\nx-injected: value"}, {"PAYOS_ENABLED": "true"},
    {"PAYOS_CHECKSUM_KEY": "bad\ud800key"},
    {"PAYOS_TIMEOUT_SECONDS": 0.0}, {"PAYOS_MAX_PAYLOAD_BYTES": True},
])
def test_enabled_configuration_requires_valid_explicit_values(changes):
    with pytest.raises(ValidationError) as error:
        configured(**changes)
    assert "FAKE_API_KEY" not in str(error.value)
    assert PUBLIC_EXAMPLE_CHECKSUM not in str(error.value)


def test_documented_webhook_vector_verifies_without_network(make_gateway):
    assert signed(webhook_data())["signature"] == PUBLIC_EXAMPLE_SIGNATURE
    gateway = make_gateway()
    verified = gateway.verify_webhook(raw_webhook(), expectation())
    assert (verified.order_code, verified.payment_link_id, verified.amount, verified.currency,
        verified.account_number, verified.reference) == (123, LINK_ID, 3000, "VND", ACCOUNT, "TF230204212323")
    assert verified.transaction_date_time == "2023-02-04 18:25:00"  # No invented timezone/date conversion.
    assert ACCOUNT not in repr(verified)
    assert gateway.verify_webhook(raw_webhook()) == verified  # Dedup/expiry belongs to the service.


def test_create_wire_contract_uses_literal_sdk_canonical_vector(make_gateway):
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == API_BASE_URL + "/v2/payment-requests"
        assert request.method == "POST"
        assert request.headers["x-client-id"] == "FAKE_CLIENT_ID"
        assert request.headers["x-api-key"] == "FAKE_API_KEY"
        body = json.loads(request.content)
        assert body == {"orderCode": 123, "amount": 3000, "description": "PARK123",
            "returnUrl": "https://parking.example/return?order=123&view=qr",
            "cancelUrl": "https://parking.example/cancel?order=123&view=qr", "expiredAt": 1_790_000_000,
            "signature": "fcc1ea5f7f9eef51a724ec0abf67f5c3dfd894aa0ef1696318b145b6a7b2c282"}
        assert request.extensions["timeout"] == {"connect": 5.0, "read": 10.0, "write": 10.0, "pool": 10.0}
        assert PUBLIC_EXAMPLE_CHECKSUM.encode() not in request.content
        return httpx.Response(200, json=signed(created_data()))
    created = make_gateway(handler).create_link(request_data())
    assert created.payment_link_id == LINK_ID and created.amount == 3000
    assert created.status == "PENDING" and len(calls) == 1


@pytest.mark.parametrize("reason,signature", [
    ("Customer request", "5d82a31550cd2d97f97961aa79c5f8b19cac26af2e20d1e266c7c654469ef8b3"),
    (None, "3a62440265a64fe6a23aa28e1a7261fe3c7e7269302474b776d9ddd21aabc270"),
])
def test_cancel_body_and_signature_do_not_imply_refund(make_gateway, reason, signature):
    def handler(request):
        assert str(request.url) == API_BASE_URL + "/v2/payment-requests/123/cancel"
        assert request.method == "POST"
        assert json.loads(request.content) == ({"cancellationReason": reason} if reason else {}) | {"signature": signature}
        # Payment may already have won the race; the adapter must return PAID.
        return httpx.Response(200, json=signed(link_data()))
    state = make_gateway(handler).cancel_link(expectation(), reason)
    assert state.is_fully_paid and state.status == "PAID"


def test_get_validates_stable_identity_and_freezes_transactions(make_gateway):
    def handler(request):
        assert request.method == "GET" and request.url.path == "/v2/payment-requests/123"
        return httpx.Response(200, json=signed(link_data()))
    state = make_gateway(handler).get_link(expectation())
    assert state.is_fully_paid and state.transactions[0].amount == 3000
    assert isinstance(state.transactions, tuple)
    with pytest.raises(ValidationError):
        state.amount_paid = 0


@pytest.mark.parametrize("changes", [
    {"amount": True}, {"amount": 3000.0}, {"amount": "3000"}, {"amount": -1}, {"amount": 0},
    {"amount": 9_007_199_254_740_992}, {"order_code": True}, {"order_code": 0},
    {"expires_at": 2_147_483_648}, {"description": "TOO-LONG-DESCRIPTION"}, {"description": "  "},
    {"return_url": "http://parking.example/return"}, {"cancel_url": "https://user:password@parking.example"},
    {"return_url": "https://parking.example/\ud800"},
])
def test_create_snapshot_rejects_invalid_values_before_http(changes):
    with pytest.raises(ValidationError):
        request_data(**changes)


@pytest.mark.parametrize("reason", [True, 42, "", "  ", "x" * 501, "bad\ud800reason"])
def test_cancel_rejects_invalid_reason_without_http(make_gateway, reason):
    with pytest.raises(PayOSInputError):
        make_gateway().cancel_link(expectation(), reason)


@pytest.mark.parametrize("raw", [
    b"", b"[]", b"null", b"\xff", b'{"data":{},"data":{}}',
    b'{"data":{"amount":3000,"amount":5000}}', b'{"data":{"amount":NaN}}',
    b'{"data":{"amount":3e3}}', b'{"data":{"amount":3000.0}}',
    b'{"data":{"amount":9007199254740992}}',
])
def test_strict_json_rejects_ambiguous_payloads(make_gateway, raw):
    with pytest.raises(PayOSProtocolError):
        make_gateway().verify_webhook(raw)


@pytest.mark.parametrize("signature", [None, "", "0" * 64, "F" * 64, "x" * 65, True])
def test_webhook_requires_valid_constant_time_signature(make_gateway, signature):
    payload = json.loads(raw_webhook())
    payload["signature"] = signature
    with pytest.raises(PayOSSignatureError):
        make_gateway().verify_webhook(json.dumps(payload).encode())


def test_signature_comparison_uses_compare_digest(make_gateway, monkeypatch):
    calls = []
    original = hmac.compare_digest
    def compare(left, right):
        calls.append((left, right))
        return original(left, right)
    monkeypatch.setattr("expansion.payos_gateway.hmac.compare_digest", compare)
    make_gateway().verify_webhook(raw_webhook())
    assert calls == [(PUBLIC_EXAMPLE_SIGNATURE, PUBLIC_EXAMPLE_SIGNATURE)]


def test_unknown_raw_fields_are_signed_before_dto_transformation(make_gateway):
    payload = json.loads(raw_webhook())
    payload["data"]["extraProviderField"] = "changed-after-signing"
    with pytest.raises(PayOSSignatureError):
        make_gateway().verify_webhook(json.dumps(payload).encode())
    payload = signed(payload["data"], success=True)
    result = make_gateway().verify_webhook(json.dumps(payload).encode())
    assert result.reference == "TF230204212323"
    assert result.payload_digest != make_gateway().verify_webhook(raw_webhook()).payload_digest


def test_sdk_null_boolean_unicode_array_rules_on_raw_signed_data(make_gateway):
    data = webhook_data() | {"optionalNull": None, "optionalNullText": "null", "optionalUndefined": "undefined",
        "booleanTrue": True, "booleanFalse": False, "items": [{"z": "Vé tháng", "a": 1}]}
    payload = signed(data, success=True)
    # The production implementation must consume these raw fields even though the
    # typed webhook DTO intentionally has no optionalNull/boolean/items fields.
    result = make_gateway().verify_webhook(json.dumps(payload, ensure_ascii=False).encode())
    assert result.reference == "TF230204212323"
    tampered = copy.deepcopy(payload)
    tampered["data"]["items"][0]["z"] = "Vé ngày"
    with pytest.raises(PayOSSignatureError):
        make_gateway().verify_webhook(json.dumps(tampered, ensure_ascii=False).encode())


@pytest.mark.parametrize("envelope_changes,data_changes", [
    ({"code": "01"}, {}), ({"success": False}, {}), ({"success": 1}, {}), ({"success": "true"}, {}),
    ({}, {"code": "01"}), ({}, {"code": "UNKNOWN"}),
])
def test_signed_but_unsuccessful_webhook_fails_closed(make_gateway, envelope_changes, data_changes):
    payload = signed(webhook_data() | data_changes, success=True) | envelope_changes
    with pytest.raises(PayOSProviderError):
        make_gateway().verify_webhook(json.dumps(payload).encode())


@pytest.mark.parametrize("changes,error_type", [
    ({"amount": True}, PayOSProtocolError), ({"amount": "3000"}, PayOSProtocolError),
    ({"orderCode": True}, PayOSProtocolError), ({"reference": ""}, PayOSProtocolError),
    ({"paymentLinkId": "../other"}, PayOSProtocolError),
    ({"transactionDateTime": "yesterday"}, PayOSProtocolError),
    ({"transactionDateTime": "2026-02-31 12:30:00"}, PayOSProtocolError),
    ({"currency": "USD"}, PayOSMismatchError), ({"accountNumber": "87654321"}, PayOSMismatchError),
    ({"amount": 3001}, PayOSMismatchError), ({"orderCode": 124}, PayOSMismatchError),
    ({"paymentLinkId": "other-link"}, PayOSMismatchError),
])
def test_financial_identity_must_match_local_snapshot(make_gateway, changes, error_type):
    payload = signed(webhook_data() | changes, success=True)
    with pytest.raises(error_type) as error:
        make_gateway().verify_webhook(json.dumps(payload).encode(), expectation())
    if error_type is PayOSMismatchError:
        assert error.value.verified_data.reference == "TF230204212323"  # Durable quarantine evidence.
        assert ACCOUNT not in repr(error.value) and not error.value.outcome_unknown


@pytest.mark.parametrize("operation", ["create", "get", "cancel"])
def test_each_http_response_is_authenticated(operation, make_gateway):
    payload = signed(created_data() if operation == "create" else link_data())
    payload["data"]["amount"] = 9999
    gateway = make_gateway(lambda _request: httpx.Response(200, json=payload))
    with pytest.raises(PayOSSignatureError) as error:
        invoke(gateway, operation)
    assert error.value.outcome_unknown == (operation != "get")


def invoke(gateway, operation):
    if operation == "create":
        return gateway.create_link(request_data())
    if operation == "cancel":
        return gateway.cancel_link(expectation(), "Customer request")
    return gateway.get_link(expectation())


@pytest.mark.parametrize("changes", [
    {"orderCode": 124}, {"amount": 3001}, {"paymentLinkId": "bad/path"},
    {"accountNumber": "87654321"}, {"currency": "USD"}, {"expiredAt": 1_790_000_001},
])
def test_create_response_mismatch_is_unknown_outcome(make_gateway, changes):
    gateway = make_gateway(lambda _request: httpx.Response(200, json=signed(created_data(**changes))))
    with pytest.raises((PayOSMismatchError, PayOSProtocolError)) as error:
        gateway.create_link(request_data())
    assert error.value.outcome_unknown


@pytest.mark.parametrize("changes,reason", [
    ({"currency": "USD"}, "currency_mismatch"), ({"accountNumber": "87654321"}, "account_mismatch"),
    ({"transactions": [transaction(accountNumber="87654321")]}, "account_mismatch"),
    ({"orderCode": 124}, "order_mismatch"), ({"id": "other-link"}, "link_mismatch"),
])
def test_get_checks_all_supplied_financial_identity_fields(make_gateway, changes, reason):
    gateway = make_gateway(lambda _request: httpx.Response(200, json=signed(link_data(**changes))))
    with pytest.raises(PayOSMismatchError) as error:
        gateway.get_link(expectation())
    assert error.value.reason == reason and error.value.verified_data.amount_paid == 3000


@pytest.mark.parametrize("changes", [
    {"status": "UNKNOWN"}, {"status": True}, {"amountPaid": "3000"}, {"amountPaid": True},
    {"transactions": {}}, {"transactions": []}, {"amountRemaining": 1000},
    {"transactions": [transaction(), transaction()], "amountPaid": 6000},
    {"amountPaid": 2000, "transactions": [transaction(amount=2000)], "amountRemaining": 1000},
])
def test_get_rejects_unknown_or_inconsistent_financial_state(make_gateway, changes):
    gateway = make_gateway(lambda _request: httpx.Response(200, json=signed(link_data(**changes))))
    with pytest.raises(PayOSProtocolError):
        gateway.get_link(expectation())


@pytest.mark.parametrize("state,paid,remaining", [
    ("PENDING", 0, 3000), ("PROCESSING", 0, 3000), ("UNDERPAID", 1000, 2000),
    ("CANCELLED", 0, 3000), ("EXPIRED", 0, 3000), ("FAILED", 0, 3000), ("PAID", 4000, 0),
])
def test_partial_overpaid_or_nonpaid_state_does_not_claim_exact_payment(make_gateway, state, paid, remaining):
    data = link_data(status=state, amountPaid=paid, amountRemaining=remaining,
        transactions=[transaction(amount=paid)] if paid else [])
    result = make_gateway(lambda _request: httpx.Response(200, json=signed(data))).get_link(expectation())
    assert not result.is_fully_paid


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500, 503])
def test_http_error_and_redirect_never_retry_create_or_leak_provider_text(make_gateway, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="PRIVATE_PROVIDER_DETAIL FAKE_API_KEY",
            headers={"Location": "https://attacker.invalid/collect"})
    with pytest.raises(PayOSProviderError) as error:
        make_gateway(handler).create_link(request_data())
    assert len(calls) == 1 and error.value.outcome_unknown
    assert error.value.http_status == status and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_ambiguous_transport_failure_preserves_identity_and_never_resends(make_gateway, failure):
    calls = []
    def handler(request):
        calls.append(request)
        raise failure("SECRET_PROVIDER_INFORMATION", request=request)
    with pytest.raises(PayOSTransportError) as error:
        make_gateway(handler).create_link(request_data())
    assert len(calls) == 1 and json.loads(calls[0].content)["orderCode"] == 123
    assert error.value.outcome_unknown and "SECRET" not in repr(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize("raw,content_type", [
    (b"not-json", "application/json"), (b"{}", "text/html"),
    (b'{"code":"00","data":{},"signature":"missing"}', "application/json"),
])
def test_invalid_http_payload_fails_closed(make_gateway, raw, content_type):
    gateway = make_gateway(lambda _request: httpx.Response(200, content=raw, headers={"Content-Type": content_type}))
    with pytest.raises((PayOSProtocolError, PayOSSignatureError)) as error:
        gateway.create_link(request_data())
    assert error.value.outcome_unknown


def test_payload_limits_apply_to_webhook_and_streamed_http(make_gateway):
    settings = configured(PAYOS_MAX_PAYLOAD_BYTES=1024)
    gateway = make_gateway(settings=settings)
    with pytest.raises(PayOSProtocolError):
        gateway.verify_webhook(b" " * 1025)
    read_chunks = []
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(100):
                read_chunks.append(1)
                yield b" " * 1024
    gateway = make_gateway(lambda _request: httpx.Response(200, stream=Stream(),
        headers={"Content-Type": "application/json"}), settings=settings)
    with pytest.raises(PayOSProtocolError) as error:
        gateway.create_link(request_data())
    assert error.value.outcome_unknown and len(read_chunks) == 2


@pytest.mark.parametrize("headers", [
    {"Content-Length": "99999999"}, {"Content-Length": "invalid"}, {"Content-Encoding": "gzip"},
])
def test_rejects_oversize_headers_and_compression_before_body_read(make_gateway, headers):
    class UnreadableStream(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("Must reject header before reading or decompressing payload")
            yield b""
    gateway = make_gateway(lambda _request: httpx.Response(200, stream=UnreadableStream(),
        headers={"Content-Type": "application/json", **headers}))
    with pytest.raises(PayOSProtocolError):
        gateway.create_link(request_data())


def test_total_response_deadline_rejects_slow_stream(make_gateway, monkeypatch):
    timestamps = iter([0.0, 11.0])
    monkeypatch.setattr("expansion.payos_gateway.monotonic", lambda: next(timestamps))
    gateway = make_gateway(lambda _request: httpx.Response(200, json=signed(created_data())))
    with pytest.raises(PayOSTransportError) as error:
        gateway.create_link(request_data())
    assert error.value.outcome_unknown


def test_checkout_url_cannot_redirect_customer_to_unexpected_host(make_gateway):
    gateway = make_gateway(lambda _request: httpx.Response(200,
        json=signed(created_data(checkoutUrl="https://pay.payos.vn.attacker.invalid/collect"))))
    with pytest.raises(PayOSProtocolError):
        gateway.create_link(request_data())
