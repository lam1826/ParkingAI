"""Explicit cashier confirmation of a server-issued checkout quote."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class CheckoutConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_token: str = Field(min_length=1, max_length=4096, strict=True)
    payment_confirmed: StrictBool
    payment_method: Literal["cash", "transfer"] | None

    @field_validator("payment_confirmed")
    @classmethod
    def must_confirm(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Phải xác nhận đã thu tiền hoặc xác nhận lượt miễn phí.")
        return value


class BillingBasis(BaseModel):
    policy_version: Literal["entry-v1", "legacy-current-rate", "prepaid-window-v1"]
    rate_source: Literal["entry_snapshot", "legacy_current_rate", "prepaid_snapshot"]
    rate_id: int | None
    unit_price: int
    ticket_type: Literal["HOURLY", "DAILY"]
    effective_date: date | None
    billable_from: datetime
    billable_seconds: int
    billable_blocks: int


class CheckoutQuoteResponse(BaseModel):
    quote_token: str
    session_id: str
    license_plate: str
    check_in_time: datetime
    quoted_at: datetime
    expires_at: datetime
    duration_minutes: int
    parking_fee: int
    monthly_coverage_end: date | None
    slot_name: str | None
    zone_name: str | None
    billing_basis: BillingBasis | None
    prepaid: dict | None = None
    online_paid: int = 0
    balance_due: int
    paid_through: datetime | None = None
