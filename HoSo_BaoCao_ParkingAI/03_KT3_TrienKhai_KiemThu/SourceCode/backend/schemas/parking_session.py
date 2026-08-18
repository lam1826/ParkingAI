from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

# Schema gốc (khớp với models/parking_session.py)
class ParkingSessionBase(BaseModel):
    vehicle_id: int
    parking_slot_id: Optional[int] = None
    check_in_time: datetime
    check_out_time: Optional[datetime] = None
    parking_fee: Optional[float] = 0.0
    status: str = "active"  # Các trạng thái: active (đang đỗ), completed (đã ra), cancelled (hủy)

# Schema cho POST (Khi xe vào bãi)
class ParkingSessionCreate(BaseModel):
    vehicle_id: int
    parking_slot_id: Optional[int] = None
    check_in_time: Optional[datetime] = None  # Sẽ tự động lấy giờ hiện tại ở CRUD nếu không truyền

# Schema cho PUT (Khi xe ra bãi hoặc cập nhật trạng thái)
class ParkingSessionUpdate(BaseModel):
    check_out_time: Optional[datetime] = None
    parking_fee: Optional[float] = None
    status: Optional[str] = None

# Schema trả về
class ParkingSessionResponse(ParkingSessionBase):
    id: str

    model_config = ConfigDict(from_attributes=True)