"""Small payOS payment-requests adapter; no SQL, environment reads, or retries.

The caller persists a unique numeric order_code and frozen amount *before* create,
then saves payment_link_id. An outcome_unknown error must be reconciled with get;
it is never permission to create another order. The caller owns the httpx client
(use a dedicated client/transport without POST retries or secret-logging hooks).

Verified messages are evidence, not authorization to issue tickets. The service
must durably record an inbox event, check ownership/expiry/idempotency, and commit
fulfillment with its receipt. A second reference or late payment needs review.
Cancellation only cancels a link; it does not refund funds. Provider timestamps
without offsets stay strings: this module never guesses their timezone.

Wire contract: https://payos.vn/docs/api/
Canonicalization: payOSHQ/payos-lib-python src/payos/_crypto/provider.py (1.1.0).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime
from time import monotonic
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic.alias_generators import to_camel

from core.money import MAX_EXACT_VND


API_BASE_URL = "https://api-merchant.payos.vn"
MAX_EPOCH_SECONDS = 2_147_483_647  # expiredAt is Int32 in the REST contract.
OrderCode = Annotated[int, Field(strict=True, gt=0, le=MAX_EXACT_VND)]
Amount = Annotated[int, Field(strict=True, ge=0, le=MAX_EXACT_VND)]
PositiveAmount = Annotated[int, Field(strict=True, gt=0, le=MAX_EXACT_VND)]
LinkId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
Reference = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:/-]+$")]
PaymentStatus = Literal["PENDING", "PROCESSING", "UNDERPAID", "PAID", "CANCELLED", "EXPIRED", "FAILED"]


class PayOSGatewayError(RuntimeError):
    """Safe to present/log; never holds HTTP responses, headers or provider prose."""
    code = "payos_error"

    def __init__(self, *, outcome_unknown: bool = False, http_status: int | None = None):
        super().__init__(self.code)
        self.outcome_unknown = outcome_unknown
        self.http_status = http_status


class PayOSDisabledError(PayOSGatewayError):
    code = "payos_disabled"


class PayOSInputError(PayOSGatewayError):
    code = "payos_invalid_input"


class PayOSProtocolError(PayOSGatewayError):
    code = "payos_invalid_payload"


class PayOSSignatureError(PayOSGatewayError):
    code = "payos_invalid_signature"


class PayOSProviderError(PayOSGatewayError):
    code = "payos_provider_rejected"


class PayOSTransportError(PayOSGatewayError):
    code = "payos_transport_error"


class PayOSMismatchError(PayOSGatewayError):
    """Signature-valid evidence conflicts with local identity; persist for review.

verified_data is deliberately not part of exception args/repr. It is not a receipt
or a success result; callers may only use it to record a reconciliation case.
"""
    code = "payos_identity_mismatch"

    def __init__(self, verified_data, *, reason: str):
        super().__init__()
        self.verified_data = verified_data
        self.reason = reason


class PayOSSettings(BaseModel):
    """Explicit configuration object; constructing it does not inspect env/.env."""
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    PAYOS_ENABLED: bool = False
    PAYOS_CLIENT_ID: SecretStr | None = Field(default=None, repr=False)
    PAYOS_API_KEY: SecretStr | None = Field(default=None, repr=False)
    PAYOS_CHECKSUM_KEY: SecretStr | None = Field(default=None, repr=False)
    PAYOS_RECEIVER_ACCOUNT_NUMBER: SecretStr | None = Field(default=None, repr=False)
    PAYOS_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1, le=30)
    PAYOS_MAX_PAYLOAD_BYTES: int = Field(default=65_536, ge=1024, le=1_048_576)

    @model_validator(mode="after")
    def enabled_configuration(self):
        if self.PAYOS_ENABLED:
            credentials = (self.PAYOS_CLIENT_ID, self.PAYOS_API_KEY, self.PAYOS_CHECKSUM_KEY)
            if any(value is None or not value.get_secret_value().strip() for value in credentials):
                raise ValueError("Enabled payOS requires backend credentials.")
            account = self.PAYOS_RECEIVER_ACCOUNT_NUMBER
            if account is None or not re.fullmatch(r"[0-9]{1,34}", account.get_secret_value()):
                raise ValueError("Enabled payOS requires a receiver account number.")
            # Provider-generated credentials cannot contain controls or invalid UTF-8.
            if any(not re.fullmatch(r"[!-~]{1,1024}", value.get_secret_value()) for value in credentials):
                raise ValueError("Invalid payOS credential format.")
        return self


class _Input(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)


def _https_url(value: str, *, checkout: bool = False) -> str:
    try:
        value.encode("utf-8")
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.fragment or parsed.port not in {None, 443}
                or any(ord(char) <= 32 or ord(char) == 127 for char in value)
                or (checkout and parsed.hostname != "pay.payos.vn")):
            raise ValueError
    except ValueError:
        raise ValueError("Invalid payment URL.") from None
    return value


def _timestamp(value: str) -> str:
    """Validate the provider's timestamp, preserving its original offset or lack of one."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", value):
        raise ValueError("Invalid provider timestamp.")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid provider timestamp.") from None
    return value


class CreateLinkRequest(_Input):
    """Server-owned snapshot; order_code is allocated/persisted by the service."""
    order_code: OrderCode
    amount: PositiveAmount
    description: str = Field(min_length=1, max_length=9, pattern=r"^[A-Za-z0-9 ]+$")
    return_url: str = Field(max_length=2048)
    cancel_url: str = Field(max_length=2048)
    expires_at: int = Field(strict=True, gt=0, le=MAX_EPOCH_SECONDS)

    @field_validator("return_url", "cancel_url")
    @classmethod
    def check_url(cls, value):
        return _https_url(value)

    @field_validator("description")
    @classmethod
    def nonempty_description(cls, value):
        if value != value.strip() or not value:
            raise ValueError("Invalid payment description.")
        return value


class PaymentExpectation(_Input):
    order_code: OrderCode
    amount: PositiveAmount
    payment_link_id: LinkId | None = None
    currency: Literal["VND"] = "VND"


class _WireData(BaseModel):
    # Unknown fields remain in the raw HMAC input; only validated fields enter DTOs.
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore", alias_generator=to_camel,
        populate_by_name=False, hide_input_in_errors=True)


class CreatedPaymentLink(_WireData):
    order_code: OrderCode
    payment_link_id: LinkId
    amount: PositiveAmount
    currency: str = Field(min_length=3, max_length=3)
    account_number: str = Field(min_length=1, max_length=34, repr=False)
    account_name: str = Field(min_length=1, max_length=200, repr=False)
    bin: str = Field(pattern=r"^[0-9]{6}$")
    description: str = Field(max_length=1000, repr=False)
    status: PaymentStatus
    checkout_url: str = Field(max_length=2048, repr=False)
    qr_code: str = Field(min_length=1, max_length=8192, repr=False)
    expired_at: int | None = Field(default=None, strict=True, gt=0, le=MAX_EPOCH_SECONDS)

    @field_validator("checkout_url")
    @classmethod
    def check_checkout_url(cls, value):
        return _https_url(value, checkout=True)


class PaymentTransaction(_WireData):
    reference: Reference
    amount: PositiveAmount
    account_number: str = Field(min_length=1, max_length=34, repr=False)
    description: str = Field(max_length=1000, repr=False)
    transaction_date_time: str = Field(min_length=1, max_length=64)

    @field_validator("transaction_date_time")
    @classmethod
    def check_timestamp(cls, value):
        return _timestamp(value)


class PaymentLink(_WireData):
    order_code: OrderCode
    payment_link_id: LinkId = Field(alias="id")
    amount: PositiveAmount
    amount_paid: Amount
    amount_remaining: Amount
    status: PaymentStatus
    # These are absent in the documented GET result. If a response supplies them,
    # validate them too; never replace a supplied currency with a VND default.
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    account_number: str | None = Field(default=None, min_length=1, max_length=34, repr=False)
    created_at: str = Field(min_length=1, max_length=64)
    transactions: tuple[PaymentTransaction, ...]
    cancellation_reason: str | None = Field(default=None, max_length=1000, repr=False)
    canceled_at: str | None = Field(default=None, max_length=64)

    @field_validator("created_at", "canceled_at")
    @classmethod
    def check_timestamp(cls, value):
        return _timestamp(value) if value is not None else None

    @field_validator("transactions", mode="before")
    @classmethod
    def freeze_transactions(cls, value):
        if not isinstance(value, list):
            raise ValueError("Expected transaction list.")
        return tuple(value)

    @model_validator(mode="after")
    def consistent_totals(self):
        if len({row.reference for row in self.transactions}) != len(self.transactions):
            raise ValueError("Duplicate transaction reference.")
        if sum(row.amount for row in self.transactions) != self.amount_paid:
            raise ValueError("Transaction total does not match paid amount.")
        if self.amount_remaining != max(0, self.amount - self.amount_paid):
            raise ValueError("Remaining amount is inconsistent.")
        if self.status == "PAID" and self.amount_paid < self.amount:
            raise ValueError("Paid status has insufficient funds.")
        return self

    @property
    def is_fully_paid(self) -> bool:
        """Exact funds only; overpayment/other statuses still require review."""
        return self.status == "PAID" and self.amount_paid == self.amount and self.amount_remaining == 0


class VerifiedWebhook(_WireData):
    order_code: OrderCode
    payment_link_id: LinkId
    amount: PositiveAmount
    currency: str = Field(min_length=3, max_length=3)
    account_number: str = Field(min_length=1, max_length=34, repr=False)
    reference: Reference
    description: str = Field(max_length=1000, repr=False)
    transaction_date_time: str = Field(min_length=1, max_length=64)
    code: Literal["00"]
    desc: str = Field(max_length=1000, repr=False)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("transaction_date_time")
    @classmethod
    def check_timestamp(cls, value):
        return _timestamp(value)


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _reject_number(_value):
    raise ValueError("Non-integer JSON number.")


def _integer(value):
    if len(value) > 17:
        raise ValueError("Oversized integer.")
    number = int(value)
    if abs(number) > MAX_EXACT_VND:
        raise ValueError("Unsafe integer.")
    return number


def _load_json(raw: bytes, limit: int) -> dict:
    if not isinstance(raw, bytes) or not raw or len(raw) > limit:
        raise PayOSProtocolError()
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
            parse_float=_reject_number, parse_constant=_reject_number, parse_int=_integer)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise PayOSProtocolError() from None


def _canonical_data(data: dict) -> str:
    """payOS payment-requests canonicalization, NOT payout/URL encoding."""
    def scalar(value):
        if value is None or value in ("null", "undefined"):
            return ""
        if type(value) is bool:
            return "true" if value else "false"
        if type(value) is int and abs(value) <= MAX_EXACT_VND:
            return str(value)
        if isinstance(value, str):
            return value
        raise PayOSProtocolError()

    parts = []
    for key in sorted(data):
        value = data[key]
        if isinstance(value, list):
            values = []
            for item in value:
                if isinstance(item, dict):
                    # The SDK sorts immediate object keys in arrays; nested objects
                    # are outside this bounded payment contract and fail closed.
                    for child in item.values():
                        scalar(child)
                    values.append(dict(sorted(item.items())))
                else:
                    scalar(item)
                    values.append(item)
            text = json.dumps(values, separators=(",", ":"), ensure_ascii=False)
        else:
            text = scalar(value)
        parts.append(f"{key}={text}")
    return "&".join(parts)


class PayOSGateway:
    def __init__(self, settings: PayOSSettings, client: httpx.Client):
        self.settings = settings
        self.client = client

    def _require_enabled(self):
        if not self.settings.PAYOS_ENABLED:
            raise PayOSDisabledError()

    def _sign(self, text: str) -> str:
        return hmac.new(self.settings.PAYOS_CHECKSUM_KEY.get_secret_value().encode("utf-8"),
            text.encode("utf-8"), hashlib.sha256).hexdigest()

    def _signed_data(self, envelope: dict, *, webhook: bool = False) -> tuple[dict, str]:
        data, signature = envelope.get("data"), envelope.get("signature")
        if not isinstance(data, dict) or not data:
            raise PayOSProtocolError()
        if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature):
            raise PayOSSignatureError()
        try:
            canonical = _canonical_data(data)
            expected_signature = self._sign(canonical)
        except (UnicodeError, RecursionError):
            raise PayOSProtocolError() from None
        if not hmac.compare_digest(expected_signature, signature):
            raise PayOSSignatureError()
        if envelope.get("code") != "00" or (webhook and (envelope.get("success") is not True or data.get("code") != "00")):
            raise PayOSProviderError()
        if not isinstance(envelope.get("desc"), str):
            raise PayOSProtocolError()
        return data, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        self._require_enabled()
        timeout = httpx.Timeout(self.settings.PAYOS_TIMEOUT_SECONDS, connect=min(5.0, self.settings.PAYOS_TIMEOUT_SECONDS))
        headers = {"x-client-id": self.settings.PAYOS_CLIENT_ID.get_secret_value(),
            "x-api-key": self.settings.PAYOS_API_KEY.get_secret_value(), "Accept": "application/json",
            "Accept-Encoding": "identity"}
        deadline = monotonic() + self.settings.PAYOS_TIMEOUT_SECONDS
        try:
            with self.client.stream(method, API_BASE_URL + path, headers=headers, json=body,
                    timeout=timeout, follow_redirects=False, auth=None) as response:
                if response.status_code != 200:
                    raise PayOSProviderError(http_status=response.status_code)
                if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                    raise PayOSProtocolError()
                # Bound bytes before decompression as well as JSON allocation.
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise PayOSProtocolError()
                length = response.headers.get("content-length")
                if length is not None and (not re.fullmatch(r"[0-9]{1,10}", length)
                        or int(length) > self.settings.PAYOS_MAX_PAYLOAD_BYTES):
                    raise PayOSProtocolError()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() > deadline:
                        raise PayOSTransportError()
                    if len(raw) + len(chunk) > self.settings.PAYOS_MAX_PAYLOAD_BYTES:
                        raise PayOSProtocolError()
                    raw.extend(chunk)
                envelope = _load_json(bytes(raw), self.settings.PAYOS_MAX_PAYLOAD_BYTES)
                data, _digest = self._signed_data(envelope)
                return data
        except PayOSGatewayError as error:
            error.outcome_unknown = method == "POST"
            raise
        except (httpx.HTTPError, OSError, UnicodeError, RuntimeError):
            raise PayOSTransportError(outcome_unknown=method == "POST") from None

    @staticmethod
    def _parse(model, data):
        try:
            return model.model_validate(data)
        except ValidationError:
            raise PayOSProtocolError() from None

    def _match(self, result, expected: PaymentExpectation | None = None):
        if result.currency is not None and result.currency != "VND":
            raise PayOSMismatchError(result, reason="currency_mismatch")
        accounts = [row.account_number for row in result.transactions] if isinstance(result, PaymentLink) else [result.account_number]
        if isinstance(result, PaymentLink) and result.account_number is not None:
            accounts.append(result.account_number)
        receiver = self.settings.PAYOS_RECEIVER_ACCOUNT_NUMBER.get_secret_value()
        if any(account != receiver for account in accounts):
            raise PayOSMismatchError(result, reason="account_mismatch")
        if expected is not None:
            if result.order_code != expected.order_code:
                raise PayOSMismatchError(result, reason="order_mismatch")
            if result.amount != expected.amount:
                raise PayOSMismatchError(result, reason="amount_mismatch")
            if expected.payment_link_id is not None and result.payment_link_id != expected.payment_link_id:
                raise PayOSMismatchError(result, reason="link_mismatch")
        return result

    def create_link(self, request: CreateLinkRequest) -> CreatedPaymentLink:
        self._require_enabled()
        body = {"amount": request.amount, "cancelUrl": request.cancel_url, "description": request.description,
            "orderCode": request.order_code, "returnUrl": request.return_url}
        body["signature"] = self._sign("&".join(f"{key}={body[key]}" for key in sorted(body)))
        body["expiredAt"] = request.expires_at
        data = self._request("POST", "/v2/payment-requests", body)
        try:
            result = self._parse(CreatedPaymentLink, data)
            self._match(result, PaymentExpectation(order_code=request.order_code, amount=request.amount))
            if result.expired_at is not None and result.expired_at != request.expires_at:
                raise PayOSMismatchError(result, reason="expiry_mismatch")
            return result
        except PayOSGatewayError as error:
            error.outcome_unknown = True
            raise

    def get_link(self, expected: PaymentExpectation) -> PaymentLink:
        """GET has no currency field; VND belongs to the configured channel/order."""
        data = self._request("GET", f"/v2/payment-requests/{expected.order_code}")
        return self._match(self._parse(PaymentLink, data), expected)

    def cancel_link(self, expected: PaymentExpectation, reason: str | None = None) -> PaymentLink:
        self._require_enabled()
        if reason is not None and (not isinstance(reason, str) or not reason.strip() or len(reason) > 500):
            raise PayOSInputError()
        try:
            if reason is not None:
                reason.encode("utf-8")
        except UnicodeError:
            raise PayOSInputError() from None
        body = {"cancellationReason": reason} if reason is not None else {}
        body["signature"] = self._sign(_canonical_data(body))
        data = self._request("POST", f"/v2/payment-requests/{expected.order_code}/cancel", body)
        try:
            # Return authoritative state even if payment won the cancellation race.
            return self._match(self._parse(PaymentLink, data), expected)
        except PayOSGatewayError as error:
            error.outcome_unknown = True
            raise

    def verify_webhook(self, raw_payload: bytes, expected: PaymentExpectation | None = None) -> VerifiedWebhook:
        """Pure verification. Without expected, the service must look up both IDs.

Do not ACK until evidence or a mismatch review case is durable. No assumptions
about delivery order, duplicates, TTL, transaction timezone or fulfillment here.
"""
        self._require_enabled()
        envelope = _load_json(raw_payload, self.settings.PAYOS_MAX_PAYLOAD_BYTES)
        data, digest = self._signed_data(envelope, webhook=True)
        result = self._parse(VerifiedWebhook, {**data, "payloadDigest": digest})
        return self._match(result, expected)
