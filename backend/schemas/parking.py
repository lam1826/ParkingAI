from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional, List
from datetime import datetime

from core.clock import BUSINESS_TZ


class CheckInRequest(BaseModel):
    """Schema nhận dữ liệu yêu cầu Check-in.

    extra="forbid": thời gian vào, phí, trạng thái, nhân viên và vé tháng hoàn
    toàn do server quyết định — client gửi các field đó (hoặc field lạ) nhận
    422 thay vì bị âm thầm bỏ qua."""
    model_config = ConfigDict(extra="forbid")

    license_plate: str = Field(
        ..., min_length=4, max_length=15, description="Biển số xe"
    )
    vehicle_type_id: int = Field(..., description="ID loại phương tiện")
    zone_id: Optional[int] = Field(
        default=None,
        description="ID khu vực muốn đỗ (tùy chọn)"
    )
    parking_slot_id: Optional[int] = Field(
        default=None,
        description="ID vị trí đỗ do nhân viên chọn (tùy chọn, bỏ trống để hệ thống tự cấp phát)"
    )

    @field_validator("license_plate")
    @classmethod
    def format_license_plate(cls, v: str) -> str:
        """Tự động xóa khoảng trắng thừa và chuyển thành chữ in hoa."""
        return v.strip().upper()


class CheckOutRequest(BaseModel):
    """Schema validate dữ liệu đầu vào cho yêu cầu Check-out.

    extra="forbid": thời gian ra, phí, trạng thái và nhân viên xử lý hoàn toàn
    do server quyết định — client cố gửi các field đó (hoặc field lạ) phải
    nhận 422 thay vì bị âm thầm bỏ qua."""
    model_config = ConfigDict(extra="forbid")

    license_plate: str = Field(
        ..., min_length=4, max_length=15,
        description="Biển số xe cần rời bãi"
    )

    @field_validator("license_plate")
    @classmethod
    def format_license_plate(cls, v: str) -> str:
        """Tự động xóa khoảng trắng thừa và chuyển thành chữ in hoa."""
        return v.strip().upper()


class CheckOutResponse(BaseModel):
    """Schema hóa đơn trả về sau khi check-out thành công."""
    session_id: str
    license_plate: str
    check_in_time: datetime
    check_out_time: datetime
    duration_minutes: int
    parking_fee: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class SlotItemResponse(BaseModel):
    """Thông tin chi tiết của một vị trí đỗ trống."""
    id: int
    name: str
    vehicle_type_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ZoneSlotSummaryResponse(BaseModel):
    """Thống kê chỗ đỗ theo từng khu vực."""
    zone_id: Optional[int]
    zone_name: str
    total_slots: int
    occupied_slots: int
    available_slots: int
    available_slots_list: List[SlotItemResponse]

    model_config = ConfigDict(from_attributes=True)


class AvailableSlotsOverviewResponse(BaseModel):
    """Schema tổng quan trạng thái chỗ đỗ toàn bãi."""
    total_slots: int
    total_occupied: int
    total_available: int
    zones: List[ZoneSlotSummaryResponse]

    model_config = ConfigDict(from_attributes=True)

class VehicleInfoResponse(BaseModel):
    id: int
    license_plate: str
    vehicle_type_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class StaffInfoResponse(BaseModel):
    id: int
    username: str

    model_config = ConfigDict(from_attributes=True)


class ParkingSessionDetailResponse(BaseModel):
    session_id: str
    vehicle: VehicleInfoResponse
    slot_id: Optional[int] = None
    slot_name: Optional[str] = None
    zone_name: Optional[str] = None
    check_in_time: datetime
    check_out_time: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Thời gian gửi đã hoàn tất, tính bằng phút",
    )
    parking_fee: int = 0
    status: str
    handled_by_staff: Optional[StaffInfoResponse] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedParkingSearchResponse(BaseModel):
    total: int = Field(..., description="Tổng số bản ghi thỏa mãn điều kiện")
    page: int = Field(..., description="Trang hiện tại")
    size: int = Field(..., description="Số bản ghi trên mỗi trang")
    items: List[ParkingSessionDetailResponse] = Field(
        ..., description="Danh sách kết quả tìm kiếm"
    )

    model_config = ConfigDict(from_attributes=True)


class ParkingSearchQuery(BaseModel):
    """Validated query contract for the business-local session timeline.

    Database timestamps are naive Asia/Ho_Chi_Minh values. An offset-aware
    client timestamp is therefore converted to that timezone and made naive
    before comparison; a naive input is interpreted as already business-local.
    """

    model_config = ConfigDict(populate_by_name=True)

    license_plate: Optional[str] = Field(
        default=None,
        description="Lọc theo biển số xe (tìm kiếm tương đối)",
    )
    status_filter: Optional[Literal["active", "completed", "cancelled"]] = Field(
        default=None,
        alias="status",
        description="Lọc theo trạng thái (active, completed, cancelled)",
    )
    date_from: Optional[datetime] = Field(
        default=None,
        description="Lọc từ thời gian vào (ISO 8601)",
    )
    date_to: Optional[datetime] = Field(
        default=None,
        description="Lọc đến thời gian vào (ISO 8601)",
    )
    zone_id: Optional[int] = Field(default=None, gt=0)
    vehicle_type_id: Optional[int] = Field(default=None, gt=0)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=100)
    sort_by: Literal[
        "check_in_time",
        "check_out_time",
        "parking_fee",
    ] = Field(default="check_in_time")
    sort_order: str = Field(default="desc", pattern="^(asc|desc|ASC|DESC)$")

    @field_validator("date_from", "date_to")
    @classmethod
    def normalize_to_business_local(cls, value: Optional[datetime]):
        if value is None or value.tzinfo is None or value.utcoffset() is None:
            return value
        return value.astimezone(BUSINESS_TZ).replace(tzinfo=None)

    @model_validator(mode="after")
    def validate_date_range(self):
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from phải nhỏ hơn hoặc bằng date_to")
        return self
