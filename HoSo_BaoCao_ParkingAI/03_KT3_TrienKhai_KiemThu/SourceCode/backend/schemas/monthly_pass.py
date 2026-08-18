from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional
from datetime import date

# Schema gốc
class MonthlyPassBase(BaseModel):
    customer_id: int
    vehicle_id: int
    start_date: date
    end_date: date
    is_active: bool = True

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi")
        return self

# Schema cho POST (Thêm mới vé tháng)
class MonthlyPassCreate(MonthlyPassBase):
    pass

# Schema cho PUT (Gia hạn hoặc hủy kích hoạt)
class MonthlyPassUpdate(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi")
        return self

# Schema trả về
class MonthlyPassResponse(MonthlyPassBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
