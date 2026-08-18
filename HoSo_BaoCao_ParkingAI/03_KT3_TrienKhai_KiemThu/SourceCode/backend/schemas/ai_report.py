from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, date

# ==========================================
# 1. SCHEMAS CHO REQUEST BODY (Từ Client gửi lên)
# ==========================================

class DashboardQuestionRequest(BaseModel):
    """Schema cho API hỏi đáp AI (Chỉ cần truyền câu hỏi)"""
    question: str = Field(
        ...,
        min_length=1,
        description="Câu hỏi của người dùng về tình trạng bãi đỗ xe",
        json_schema_extra={"example": "Hôm nay bãi đỗ xe kiếm được bao nhiêu tiền?"}
    )

class DailyReportRequest(BaseModel):
    """Schema cho API tạo báo cáo ngày"""
    target_date: date = Field(..., description="Ngày cần tạo báo cáo")
    parking_stats: Dict[str, Any] = Field(..., description="Dữ liệu thống kê của ngày đó")

class WeeklyReportRequest(BaseModel):
    """Schema cho API tạo báo cáo tuần"""
    start_date: date
    end_date: date
    weekly_data: List[Dict[str, Any]]

class ScheduleRequest(BaseModel):
    """Schema cho API đề xuất lịch trực"""
    hourly_traffic: List[Dict[str, Any]]
    occupancy_rate: float
    revenue: float


# ==========================================
# 2. SCHEMAS CHO DATABASE OPERATIONS (Lưu lịch sử)
# ==========================================

class AiReportBase(BaseModel):
    """Schema gốc chứa các trường dùng chung cho Database"""
    report_type: str = Field(..., description="Loại báo cáo: DAILY_REPORT, WEEKLY_REPORT, DASHBOARD_QA, STAFF_SCHEDULE")
    prompt_used: str = Field(..., description="Toàn bộ prompt (bao gồm cả dữ liệu) đã gửi cho Gemini")
    content: str = Field(..., description="Kết quả trả về từ Gemini")

class AiReportCreate(AiReportBase):
    """Schema dùng khi lưu một bản ghi lịch sử mới vào DB"""
    generated_by_id: int = Field(..., description="ID của người dùng đã thực hiện truy vấn")

class AiReportUpdate(BaseModel):
    """Schema dùng khi cập nhật bản ghi (thường rất ít dùng cho AI Report)"""
    content: Optional[str] = None

class AiReportResponse(AiReportBase):
    """Schema trả về cho Client khi get danh sách lịch sử"""
    id: int
    generated_by_id: int
    created_at: datetime

    # Cấu hình Pydantic v2 để đọc dữ liệu từ SQLAlchemy ORM
    model_config = ConfigDict(from_attributes=True)

class StaffSuggestionRequest(BaseModel):
    """Input: Lưu lượng, doanh thu, tỷ lệ lấp đầy"""
    hourly_traffic: List[Dict[str, Any]] = Field(..., description="Dữ liệu lưu lượng xe ra vào theo giờ")
    revenue: float = Field(..., description="Tổng doanh thu dự kiến hoặc hiện tại")
    occupancy_rate: float = Field(..., description="Tỷ lệ lấp đầy bãi đỗ xe (VD: 0.85 cho 85%)")