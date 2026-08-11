from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.customer import CustomerResponse
from schemas.vehicle_type import VehicleTypeResponse


class VehicleBase(BaseModel):
    license_plate: str = Field(min_length=3, max_length=20)
    vehicle_type_id: int = Field(gt=0)
    customer_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("license_plate", mode="before")
    @classmethod
    def normalize_license_plate(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("customer_id", mode="before")
    @classmethod
    def empty_customer_is_none(cls, value):
        return None if value == "" else value


class VehicleCreate(VehicleBase):
    pass


class VehicleUpdate(BaseModel):
    license_plate: Optional[str] = Field(default=None, min_length=3, max_length=20)
    vehicle_type_id: Optional[int] = Field(default=None, gt=0)
    customer_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("license_plate", mode="before")
    @classmethod
    def normalize_optional_license_plate(cls, value: str | None) -> str | None:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("customer_id", mode="before")
    @classmethod
    def empty_customer_is_none(cls, value):
        return None if value == "" else value


class VehicleResponse(VehicleBase):
    id: int
    vehicle_type: VehicleTypeResponse
    customer: Optional[CustomerResponse] = None

    model_config = ConfigDict(from_attributes=True)
