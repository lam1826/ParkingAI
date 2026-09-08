"""Server-owned identity, occupancy and prices are never accepted as customer input."""
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from schemas.zone import ZoneCreate
from schemas.parking_slot import ParkingSlotCreate


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SiteCreate(StrictBody):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(default="", max_length=250)


class SiteMemberCreate(StrictBody):
    user_id: int = Field(gt=0)
    role: Literal["staff", "manager"]


class SiteZoneCreate(ZoneCreate):
    """Reuse the validated zone identity; the route owns site_id."""


class SiteSlotCreate(ParkingSlotCreate):
    """Zone ownership and capacity are validated inside the transaction."""


class BookingWindow(StrictBody):
    site_id: int = Field(gt=0)
    vehicle_id: int = Field(gt=0)
    start_at: AwareDatetime
    end_at: AwareDatetime
    request_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

    @model_validator(mode="after")
    def valid_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        if (self.end_at - self.start_at).total_seconds() > 366 * 86400:
            raise ValueError("Khoảng đặt chỗ tối đa 366 ngày.")
        return self


class ReservationCreate(BookingWindow):
    slot_id: int | None = Field(default=None, gt=0)


class AllocationCreate(ReservationCreate):
    slot_id: int = Field(gt=0)


class SiteCheckIn(StrictBody):
    license_plate: str = Field(min_length=1, max_length=20)
    vehicle_type_id: int = Field(gt=0)
    parking_slot_id: int = Field(gt=0)


class OrganizationCreate(StrictBody):
    name: str = Field(min_length=1, max_length=150)


class OrganizationMemberCreate(StrictBody):
    user_id: int = Field(gt=0)


class FleetVehicleCreate(StrictBody):
    vehicle_id: int = Field(gt=0)
