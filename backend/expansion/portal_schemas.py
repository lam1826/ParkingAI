from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from core.money import MAX_EXACT_VND


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileCreate(Input):
    full_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=8, max_length=20, pattern=r"^\+?[0-9]+$")
    email: EmailStr | None = Field(default=None, max_length=100)


class LinkRequest(Input):
    phone_number: str = Field(min_length=8, max_length=20, pattern=r"^\+?[0-9]+$")
    note: str = Field(default="", max_length=500)


class VehicleRequest(Input):
    license_plate: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9.\- ]+$")
    vehicle_type_id: int = Field(strict=True, gt=0)
    note: str = Field(default="", max_length=500)

    @field_validator("license_plate")
    @classmethod
    def canonical_plate(cls, value):
        return value.upper().replace(" ", "")


class PlanCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    site_id: int | None = Field(default=None, strict=True, gt=0)
    vehicle_type_id: int = Field(strict=True, gt=0)
    duration_days: int = Field(strict=True, ge=1, le=366)
    price: int = Field(strict=True, gt=0, le=MAX_EXACT_VND)


class OrderCreate(Input):
    plan_id: int = Field(strict=True, gt=0)
    vehicle_id: int = Field(strict=True, gt=0)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    payment_mode: Literal["demo", "manual"] = "demo"


class PlanUpdate(Input):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: int | None = Field(default=None, strict=True, gt=0, le=MAX_EXACT_VND)
    duration_days: int | None = Field(default=None, strict=True, ge=1, le=366)
    is_active: bool | None = Field(default=None, strict=True)


class Simulation(Input):
    token: str = Field(min_length=20, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    outcome: Literal["success", "failed", "cancelled"]


class Resolution(Input):
    approve: bool = Field(strict=True)
    note: str = Field(default="", max_length=500)


class ManualCollection(Input):
    payment_method: Literal["cash", "transfer"]
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Cần xác nhận đã thu tiền trước khi kích hoạt kỳ vé.")
        return value


class RefundCreate(Input):
    reason: str = Field(min_length=1, max_length=500)
