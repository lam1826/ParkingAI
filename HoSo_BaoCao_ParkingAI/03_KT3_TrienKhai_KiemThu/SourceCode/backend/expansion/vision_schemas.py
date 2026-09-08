"""Camera configuration contains no stream URL or credential."""
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CameraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    site_id: int = Field(gt=0)
    zone_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=100)
    direction: Literal["entry", "exit"] = "entry"
    is_active: bool = True
    retention_hours: int = Field(default=24, ge=1, le=72)


class CameraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    direction: Literal["entry", "exit"] | None = None
    is_active: bool | None = None
    retention_hours: int | None = Field(default=None, ge=1, le=72)

    @model_validator(mode="after")
    def no_null_changes(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Không được đặt thuộc tính camera thành null.")
        return self


class ObservationUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_id: int = Field(gt=0)
    event_id: UUID
    captured_at: datetime | None = None

    @field_validator("captured_at")
    @classmethod
    def aware_capture(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("captured_at phải có múi giờ.")
        return value


class ObservationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "reject"]
    license_plate: str | None = Field(default=None, min_length=3, max_length=20)

    @field_validator("license_plate")
    @classmethod
    def plate(cls, value):
        if value is not None:
            value = value.strip().upper()
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9 .-]{1,18}[A-Z0-9]", value):
                raise ValueError("Biển số chỉ gồm chữ, số, dấu cách, dấu chấm và gạch ngang.")
        return value

    @model_validator(mode="after")
    def accepted_plate_required(self):
        if self.decision == "accept" and not self.license_plate:
            raise ValueError("Nhân viên phải kiểm tra và xác nhận biển số.")
        if self.decision == "reject" and self.license_plate is not None:
            raise ValueError("Không gửi biển số khi từ chối ảnh.")
        return self
