from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date, datetime
from schemas.checkout import CheckoutConfirmation

# Schema gốc (khớp với models/parking_session.py)
class ParkingSessionBase(BaseModel):
    vehicle_id: int
    parking_slot_id: Optional[int] = None
    check_in_time: datetime
    check_out_time: Optional[datetime] = None
    parking_fee: Optional[int] = 0
    status: str = "active"  # Các trạng thái: active (đang đỗ), completed (đã ra), cancelled (hủy)

# Schema cho POST (Khi xe vào bãi): check_in_time hoàn toàn do SERVER quyết
# định (crud dùng server_now()) — client gửi thời gian/phí/trạng thái/staff/
# vé tháng hoặc field lạ đều nhận 422 nhờ extra="forbid".
class ParkingSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_id: int
    parking_slot_id: Optional[int] = None


# ParkingSessionUpdate và crud.update_parking_session đã bị xóa (Đợt 5):
# không còn caller nào, và bề mặt update rộng chứa field tài chính/thời gian
# là rủi ro nếu ai đó nối lại vào router.


class CheckOutBody(CheckoutConfirmation):
    """Confirm a signed quote; billing and exit time remain server-owned."""

# Schema trả về
class ParkingSessionResponse(ParkingSessionBase):
    id: str
    monthly_coverage_end: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)
