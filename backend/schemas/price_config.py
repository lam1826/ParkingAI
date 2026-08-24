from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal, Optional
from datetime import date

# Schema gốc (khớp với models/price_config.py và cách ParkingService.calculate_fee sử dụng)
class PriceConfigBase(BaseModel):
    vehicle_type_id: int
    ticket_type: Literal["HOURLY", "DAILY"]
    price: float = Field(..., ge=0)
    effective_date: date       # Ngày bắt đầu áp dụng
    is_active: bool = True     # Trạng thái áp dụng

# Schema cho POST
class PriceConfigCreate(PriceConfigBase):
    model_config = ConfigDict(extra="forbid")

# Schema cho PUT
class PriceConfigUpdate(BaseModel):
    vehicle_type_id: Optional[int] = None
    ticket_type: Optional[Literal["HOURLY", "DAILY"]] = None
    price: Optional[float] = Field(default=None, ge=0)
    effective_date: Optional[date] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, data):
        """Partial update: field bị BỎ QUA thì hợp lệ, nhưng field có mặt với
        giá trị null phải bị từ chối 422 — mọi cột của bảng giá đều bắt buộc,
        không có trạng thái NULL hợp lệ. Chặn tại Pydantic để router không
        nhận None rồi merge sai hoặc ghi NULL vào cột NOT NULL."""
        if isinstance(data, dict):
            null_fields = [
                key for key in cls.model_fields if key in data and data[key] is None
            ]
            if null_fields:
                raise ValueError(
                    "Các field sau không được phép là null: "
                    + ", ".join(null_fields)
                    + ". Hãy bỏ hẳn field khỏi payload nếu không muốn cập nhật."
                )
        return data

# Schema trả về
class PriceConfigResponse(PriceConfigBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
