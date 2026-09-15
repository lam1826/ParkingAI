"""Backend-only configuration and small, secret-free customer DTOs."""
import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from expansion.payos_gateway import PayOSSettings, _https_url


class OnlinePaymentConfig(BaseSettings):
    # Explicit OS environment only; never discover an application .env file here.
    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True, hide_input_in_errors=True)
    PAYOS_ENABLED: bool = False
    PAYOS_CLIENT_ID: SecretStr | None = Field(default=None, repr=False)
    PAYOS_API_KEY: SecretStr | None = Field(default=None, repr=False)
    PAYOS_CHECKSUM_KEY: SecretStr | None = Field(default=None, repr=False)
    PAYOS_RECEIVER_ACCOUNT_NUMBER: SecretStr | None = Field(default=None, repr=False)
    PAYOS_TIMEOUT_SECONDS: float = Field(default=10.0, ge=1, le=30)
    PAYOS_MAX_PAYLOAD_BYTES: int = Field(default=65_536, ge=1024, le=1_048_576)
    PAYOS_SITE_ID: int | None = Field(default=None, gt=0)
    PAYOS_RETURN_URL: str | None = None
    PAYOS_CANCEL_URL: str | None = None

    @model_validator(mode="after")
    def enabled_fields(self):
        if self.PAYOS_ENABLED:
            self.adapter_settings()
            if self.PAYOS_SITE_ID is None or self.PAYOS_RETURN_URL is None or self.PAYOS_CANCEL_URL is None:
                raise ValueError("Enabled payOS requires a site and backend return/cancel URLs.")
            _https_url(self.PAYOS_RETURN_URL)
            _https_url(self.PAYOS_CANCEL_URL)
        return self

    def adapter_settings(self):
        return PayOSSettings(**{key: getattr(self, key) for key in PayOSSettings.model_fields})

    @property
    def channel(self):
        return hashlib.sha256(self.PAYOS_CLIENT_ID.get_secret_value().encode()).hexdigest()

    @property
    def receiver_digest(self):
        return hashlib.sha256(self.PAYOS_RECEIVER_ACCOUNT_NUMBER.get_secret_value().encode()).hexdigest()


def get_online_payment_config():
    return OnlinePaymentConfig(_env_file=None)


class LinkCancellation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=200)


class ReviewDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["note", "confirmed_external_refund"]
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    reason: str = Field(min_length=3, max_length=500)
    refund_amount: int | None = Field(default=None, strict=True, gt=0, le=9_007_199_254_740_991)
    external_reference: str | None = Field(default=None, min_length=3, max_length=120)
    confirmed: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def explicit_external_action(self):
        if self.action == "confirmed_external_refund":
            if not self.confirmed or self.refund_amount is None or self.external_reference is None:
                raise ValueError("Cần xác nhận đã hoàn tiền ngoài hệ thống, số tiền và mã chứng từ.")
        elif self.refund_amount is not None or self.external_reference is not None or self.confirmed:
            raise ValueError("Ghi chú không được kèm thông tin hoàn tiền.")
        return self


class PaymentLinkView(BaseModel):
    order_id: str
    provider: Literal["payos"] = "payos"
    enabled: bool
    state: Literal["not_created", "creating", "unknown", "ready", "paid", "cancelled", "expired", "review"]
    provider_status: str | None = None
    amount: int
    currency: Literal["VND"] = "VND"
    expires_at: datetime
    server_now: datetime
    checkout_url: str | None = None
    qr_code: str | None = None
    qr_svg: str | None = None
    review_reason: str | None = None
    message: str
    can_create: bool
    can_refresh: bool
    can_cancel: bool
