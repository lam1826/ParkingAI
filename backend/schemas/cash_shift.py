from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from core.money import MAX_EXACT_VND


class CashShiftOpen(BaseModel):
    opening_cash: StrictInt = Field(default=0, ge=0, le=MAX_EXACT_VND)
    model_config = ConfigDict(extra="forbid")


class CashShiftClose(BaseModel):
    counted_cash: StrictInt = Field(ge=0, le=MAX_EXACT_VND)
    model_config = ConfigDict(extra="forbid")


class CashShiftResponse(BaseModel):
    id: str
    staff_id: int
    site_id: int | None = None
    staff_name: str
    opened_at: datetime
    closed_at: datetime | None
    status: Literal["open", "closed"]
    opening_cash: int
    counted_cash: int | None
    expected_cash: int
    difference: int | None
    cash_receipts: int
    cash_refunds: int
    transfer_receipts: int
    transfer_refunds: int
    net_revenue: int
    payment_count: int


class CashShiftListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[CashShiftResponse]
