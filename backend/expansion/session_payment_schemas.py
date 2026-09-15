"""Only request identities come from clients; all amounts are server-owned."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from expansion.online_payment_schemas import PaymentLinkView


class SessionPaymentConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    SESSION_FEE_QUOTE_TTL_SECONDS: int = Field(default=300, ge=60, le=900)


class SessionFeeQuoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class SessionFeeQuoteView(BaseModel):
    id: str
    session_id: str
    gross_fee: int
    online_paid: int
    balance_due: int
    quoted_at: datetime
    paid_through: datetime
    expires_at: datetime
    server_now: datetime
    status: str
    billing_basis: dict


class SessionPaymentLinkView(PaymentLinkView):
    # A session fee is not a portal purchase. Never manufacture a portal order ID.
    order_id: None = None
    quote_id: str
    session_id: str
    paid_through: datetime
