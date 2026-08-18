from pydantic import BaseModel, ConfigDict, Field
from typing import List

class PeakHourItem(BaseModel):
    hour: str = Field(..., description="Khung giờ (VD: 08:00 - 09:00)")
    count: int = Field(..., description="Số lượng xe check-in trong khung giờ")

    model_config = ConfigDict(from_attributes=True)

class DashboardResponse(BaseModel):
    total_vehicles_today: int = Field(..., description="Tổng số xe vào bãi trong ngày hôm nay")
    total_revenue_today: float = Field(..., description="Tổng doanh thu trong ngày hôm nay")
    vehicles_currently_inside: int = Field(..., description="Số lượng xe hiện đang còn trong bãi")
    vehicles_checked_out_today: int = Field(..., description="Số lượng xe đã hoàn tất rời bãi trong ngày")
    occupancy_rate_percentage: float = Field(..., description="Tỷ lệ lấp đầy bãi đỗ hiện tại (%)")
    top_peak_hours: List[PeakHourItem] = Field(..., description="Top 5 giờ cao điểm có lượng xe vào đông nhất")

    model_config = ConfigDict(from_attributes=True)

class AIInsightResponse(BaseModel):
    insight: str = Field(..., description="Nội dung phân tích và gợi ý từ AI Gemini")

    model_config = ConfigDict(from_attributes=True)

class RecentSessionItem(BaseModel):
    id: str = Field(..., description="Mã phiên gửi xe")
    plate: str = Field(..., description="Biển số xe")
    vehicleType: str = Field(..., description="Loại xe")
    timeIn: str = Field(..., description="Thời gian xe vào bãi (ISO datetime)")
    status: str = Field(..., description="Trạng thái hiển thị: 'Đang đỗ' hoặc 'Đã rời bãi'")

    model_config = ConfigDict(from_attributes=True)

class RevenueChartItem(BaseModel):
    day: str = Field(..., description="Ngày (VD: 24/07)")
    revenue: float = Field(..., description="Doanh thu trong ngày")

    model_config = ConfigDict(from_attributes=True)