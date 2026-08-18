from pydantic import BaseModel, ConfigDict, Field
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
    pass

# Schema cho PUT
class PriceConfigUpdate(BaseModel):
    vehicle_type_id: Optional[int] = None
    ticket_type: Optional[Literal["HOURLY", "DAILY"]] = None
    price: Optional[float] = Field(default=None, ge=0)
    effective_date: Optional[date] = None
    is_active: Optional[bool] = None

# Schema trả về
class PriceConfigResponse(PriceConfigBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
