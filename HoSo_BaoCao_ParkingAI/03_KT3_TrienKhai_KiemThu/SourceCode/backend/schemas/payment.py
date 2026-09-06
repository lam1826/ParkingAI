from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from core.money import MAX_EXACT_VND

PaymentMethod = Literal["cash", "transfer"]
PaymentSource = Literal["parking_session", "monthly_pass"]
PaymentKind = Literal["receipt", "refund"]


class RefundCreate(BaseModel):
    amount: StrictInt = Field(gt=0, le=MAX_EXACT_VND)
    method: PaymentMethod = "cash"
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    model_config = ConfigDict(extra="forbid")

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class PaymentResponse(BaseModel):
    id: str
    source_type: PaymentSource
    source_id: str
    kind: PaymentKind
    amount: int
    method: Literal["cash", "transfer", "legacy_unknown"]
    collected_by_id: int | None
    shift_id: str | None
    created_at: datetime
    original_payment_id: str | None
    reason: str | None
    refunded_amount: int = 0
    refundable_amount: int = 0
    model_config = ConfigDict(from_attributes=True)


class PaymentListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[PaymentResponse]
