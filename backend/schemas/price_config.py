from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date

# Schema gốc (khớp với models/price_config.py và cách ParkingService.calculate_fee sử dụng)
class PriceConfigBase(BaseModel):
    vehicle_type_id: int
    ticket_type: str          # 'HOURLY', 'DAILY', 'MONTHLY'
    price: float               # Đơn giá theo ticket_type
    effective_date: date       # Ngày bắt đầu áp dụng
    is_active: bool = True     # Trạng thái áp dụng

# Schema cho POST
class PriceConfigCreate(PriceConfigBase):
    pass

# Schema cho PUT
class PriceConfigUpdate(BaseModel):
    vehicle_type_id: Optional[int] = None
    ticket_type: Optional[str] = None
    price: Optional[float] = None
    effective_date: Optional[date] = None
    is_active: Optional[bool] = None

# Schema trả về
class PriceConfigResponse(PriceConfigBase):
    id: int

    model_config = ConfigDict(from_attributes=True)