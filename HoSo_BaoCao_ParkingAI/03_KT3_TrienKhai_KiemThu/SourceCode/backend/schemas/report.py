from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime


class RevenueReportResponse(BaseModel):
    """Schema trả về báo cáo doanh thu."""
    filter_type: str = Field(..., description="Loại thống kê (day, week, month, year)")
    start_date: datetime = Field(..., description="Thời gian bắt đầu thống kê")
    end_date: datetime = Field(..., description="Thời gian kết thúc thống kê")
    total_trips: int = Field(..., description="Tổng lượt gửi xe hoàn tất")
    total_revenue: float = Field(..., description="Tổng doanh thu")
    average_fee: float = Field(..., description="Trung bình phí mỗi lượt")
    most_frequent_vehicle_type: Optional[str] = Field(
        None,
        description="Loại xe xuất hiện nhiều nhất"
    )

    model_config = ConfigDict(from_attributes=True)


class TrafficItem(BaseModel):
    """Cấu trúc một mục thống kê lưu lượng."""
    time_label: str = Field(
        ...,
        description="Nhãn thời gian (Giờ, Ngày, Tuần hoặc Tháng)"
    )
    total_vehicles: int = Field(
        ...,
        description="Tổng số lượt xe"
    )

    model_config = ConfigDict(from_attributes=True)


class TrafficReportResponse(BaseModel):
    """Schema tổng quan báo cáo lưu lượng giao thông bãi đỗ."""
    traffic_by_hour: List[TrafficItem] = Field(
        ...,
        description="Lưu lượng phân bổ theo giờ trong ngày"
    )
    traffic_by_day: List[TrafficItem] = Field(
        ...,
        description="Lưu lượng phân bổ theo ngày"
    )
    traffic_by_week: List[TrafficItem] = Field(
        ...,
        description="Lưu lượng phân bổ theo tuần"
    )
    traffic_by_month: List[TrafficItem] = Field(
        ...,
        description="Lưu lượng phân bổ theo tháng"
    )

    model_config = ConfigDict(from_attributes=True)