from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Any, Optional

# Trạng thái chiếm chỗ do check-in/check-out của server quản lý. Client chỉ
# được cấu hình danh tính, khu vực, loại xe và trạng thái sử dụng của slot.
class ParkingSlotWriteBase(BaseModel):
    slot_name: str = Field(..., min_length=1, max_length=50)
    zone_id: int
    vehicle_type_id: int
    is_active: bool = True

    model_config = ConfigDict(extra="forbid")

    @field_validator("slot_name")
    @classmethod
    def normalize_slot_name(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Mã vị trí không được để trống")
        return normalized

# Schema cho POST
class ParkingSlotCreate(ParkingSlotWriteBase):
    pass

# Schema cho PUT
class ParkingSlotUpdate(BaseModel):
    slot_name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    zone_id: Optional[int] = None
    vehicle_type_id: Optional[int] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field in ("slot_name", "zone_id", "vehicle_type_id", "is_active"):
                if field in data and data[field] is None:
                    raise ValueError(f"{field} không được nhận giá trị null")
        return data

    @field_validator("slot_name")
    @classmethod
    def normalize_slot_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Mã vị trí không được để trống")
        return normalized

# Schema trả về cho GET, POST, PUT
class ParkingSlotResponse(ParkingSlotWriteBase):
    id: int
    is_occupied: bool

    model_config = ConfigDict(from_attributes=True)
