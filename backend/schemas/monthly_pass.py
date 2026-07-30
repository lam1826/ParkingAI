from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date

# Schema gốc
class MonthlyPassBase(BaseModel):
    customer_id: int
    vehicle_id: int
    start_date: date
    end_date: date
    is_active: bool = True

# Schema cho POST (Thêm mới vé tháng)
class MonthlyPassCreate(MonthlyPassBase):
    pass

# Schema cho PUT (Gia hạn hoặc hủy kích hoạt)
class MonthlyPassUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None

# Schema trả về
class MonthlyPassResponse(MonthlyPassBase):
    id: int

    model_config = ConfigDict(from_attributes=True)