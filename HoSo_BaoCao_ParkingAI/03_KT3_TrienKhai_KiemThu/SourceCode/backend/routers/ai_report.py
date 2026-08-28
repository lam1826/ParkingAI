import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Dict, Any
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database import get_db
from core.config import settings
from schemas import ai_report as ai_report_schema
from services.ai_service import AIService
from services.parking_service import ParkingService
from services.report_service import ReportService
from models.ai_report import AiReport
from typing import Optional

# IMPORT ĐÚNG: Lấy hàm get_current_user độc lập từ services.auth_service
from services.auth_service import RoleChecker, get_current_user
from models.user import User

router = APIRouter(
    prefix="/ai",
    tags=["AI Analytics"],
    dependencies=[Depends(RoleChecker("staff"))],
)

MAX_AI_QUESTION_CHARS = 1_000
MAX_CUSTOM_COLLECTION_ITEMS = 100
MAX_WEEKLY_ITEMS = 7
MAX_HOURLY_ITEMS = 24
MAX_CUSTOM_JSON_BYTES = 32 * 1024


def _validate_custom_payload(
    value: Any,
    *,
    field_name: str,
    top_level_limit: int,
) -> Any:
    """Bound user-supplied context before aggregation or provider setup.

    HTTP JSON can contain small top-level collections with a very large nested
    value.  Therefore both every nested collection's item count and the UTF-8
    serialized size are bounded.
    """
    if value is None:
        return value
    if len(value) > top_level_limit:
        raise ValueError(
            f"{field_name} chỉ được chứa tối đa {top_level_limit} phần tử"
        )

    pending = list(value.values()) if isinstance(value, dict) else list(value)
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if len(item) > MAX_CUSTOM_COLLECTION_ITEMS:
                raise ValueError(
                    f"Mỗi object trong {field_name} chỉ được chứa tối đa "
                    f"{MAX_CUSTOM_COLLECTION_ITEMS} phần tử"
                )
            pending.extend(item.values())
        elif isinstance(item, list):
            if len(item) > MAX_CUSTOM_COLLECTION_ITEMS:
                raise ValueError(
                    f"Mỗi danh sách trong {field_name} chỉ được chứa tối đa "
                    f"{MAX_CUSTOM_COLLECTION_ITEMS} phần tử"
                )
            pending.extend(item)

    try:
        encoded_size = len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{field_name} không phải dữ liệu JSON hợp lệ") from exc
    if encoded_size > MAX_CUSTOM_JSON_BYTES:
        raise ValueError(
            f"{field_name} vượt giới hạn {MAX_CUSTOM_JSON_BYTES} byte"
        )
    return value

# ==========================================
# SCHEMAS DÀNH RIÊNG CHO REQUEST BODY
# ==========================================
class DailyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_date: date
    # Bỏ trống -> backend tự tổng hợp từ database (luồng chuẩn).
    # Nếu client gửi thì không được gửi dict rỗng.
    parking_stats: Optional[Dict[str, Any]] = Field(default=None, min_length=1)

    @field_validator("parking_stats")
    @classmethod
    def validate_parking_stats(cls, value):
        return _validate_custom_payload(
            value,
            field_name="parking_stats",
            top_level_limit=MAX_CUSTOM_COLLECTION_ITEMS,
        )

class WeeklyReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    # Bỏ trống -> backend tự tổng hợp theo từng ngày trong khoảng đã chọn.
    weekly_data: Optional[List[Dict[str, Any]]] = Field(default=None, min_length=1)

    @field_validator("weekly_data")
    @classmethod
    def validate_weekly_data(cls, value):
        return _validate_custom_payload(
            value,
            field_name="weekly_data",
            top_level_limit=MAX_WEEKLY_ITEMS,
        )

    @model_validator(mode="after")
    def validate_date_range(self):
        if (self.end_date - self.start_date).days != 6:
            raise ValueError("Báo cáo tuần phải bao gồm đúng 7 ngày liên tiếp")
        return self

class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        ...,
        min_length=1,
        max_length=MAX_AI_QUESTION_CHARS,
        description="Câu hỏi của người dùng",
    )
    parking_stats: Dict[str, Any] = Field(min_length=1)

    @field_validator("parking_stats")
    @classmethod
    def validate_parking_stats(cls, value):
        return _validate_custom_payload(
            value,
            field_name="parking_stats",
            top_level_limit=MAX_CUSTOM_COLLECTION_ITEMS,
        )

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Câu hỏi không được để trống")
        return value

class DashboardQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        ...,
        min_length=1,
        max_length=MAX_AI_QUESTION_CHARS,
        description="Câu hỏi của người dùng về tình trạng bãi đỗ xe",
        json_schema_extra={"example": "Hôm nay bãi đỗ xe kiếm được bao nhiêu tiền?"}
    )

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Câu hỏi không được để trống")
        return value

# BỔ SUNG: SCHEMA CHO API GỢI Ý NHÂN SỰ
class StaffSuggestionRequest(BaseModel):
    """Input: Lưu lượng, doanh thu, tỷ lệ lấp đầy.
    Bỏ trống toàn bộ -> backend tự tổng hợp từ database."""
    model_config = ConfigDict(extra="forbid")

    hourly_traffic: Optional[List[Dict[str, Any]]] = Field(default=None, min_length=1, description="Dữ liệu lưu lượng xe ra vào theo giờ")
    revenue: Optional[float] = Field(default=None, ge=0, description="Tổng doanh thu dự kiến hoặc hiện tại")
    occupancy_rate: Optional[float] = Field(default=None, ge=0, le=100, description="Tỷ lệ lấp đầy bãi đỗ xe từ 0 đến 100%")

    @field_validator("hourly_traffic")
    @classmethod
    def validate_hourly_traffic(cls, value):
        return _validate_custom_payload(
            value,
            field_name="hourly_traffic",
            top_level_limit=MAX_HOURLY_ITEMS,
        )


# ==========================================
# 1. CÁC API SINH BÁO CÁO (SỬ DỤNG AI_SERVICE)
# ==========================================
@router.post("/daily-report")
def create_daily_report(
    req: DailyReportRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI phân tích và sinh báo cáo bãi đỗ xe theo ngày.
    Nếu client không gửi parking_stats, backend tự tổng hợp từ database."""
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)

    parking_stats = req.parking_stats
    if parking_stats is None:
        parking_stats = ParkingService(db).get_parking_statistics(
            target_date=req.target_date
        )

    report_text = ai_service.generate_daily_report(
        target_date=req.target_date,
        parking_stats=parking_stats,
        user_id=current_user.id
    )
    return {"message": "Tạo báo cáo thành công", "content": report_text}

@router.post("/weekly-report")
def create_weekly_report(
    req: WeeklyReportRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI phân tích xu hướng hoạt động tuần.
    Nếu client không gửi weekly_data, backend tự tổng hợp theo từng ngày."""
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)

    weekly_data = req.weekly_data
    if weekly_data is None:
        weekly_data = ParkingService(db).get_daily_summaries(
            start_date=req.start_date,
            end_date=req.end_date
        )

    report_text = ai_service.generate_weekly_report(
        start_date=req.start_date,
        end_date=req.end_date,
        weekly_data=weekly_data,
        user_id=current_user.id
    )
    return {"message": "Tạo báo cáo tuần thành công", "content": report_text}

@router.post("/ask")
def ask_ai_question(
    req: QuestionRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Hỏi đáp ngôn ngữ tự nhiên về dữ liệu bãi đỗ xe (Client tự gửi dữ liệu)"""
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)
    answer = ai_service.answer_question(
        question=req.question,
        parking_stats=req.parking_stats,
        user_id=current_user.id
    )
    return {"message": "Truy vấn thành công", "content": answer}

@router.post("/question")
def ask_ai_question_from_dashboard(
    req: DashboardQuestionRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    API Hỏi đáp thông minh với dữ liệu Dashboard:
    - Client chỉ cần gửi câu hỏi (ví dụ: 'Hôm nay có bao nhiêu xe đang trong bãi?').
    - Server sẽ tự động lấy dữ liệu tổng quan trong ngày, ghép vào ngữ cảnh và nhờ AI trả lời.
    - Đã khóa chức năng suy diễn của AI.
    """
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)
    
    answer = ai_service.ask_dashboard_question(
        question=req.question,
        user_id=current_user.id
    )
    
    return {
        "message": "Truy vấn Dashboard thành công",
        "question": req.question, 
        "content": answer
    }

# =========================================================
# API MỚI: ĐỀ XUẤT NHÂN SỰ DỰA TRÊN DỮ LIỆU
# =========================================================
@router.post("/staff-suggestion")
def suggest_staff(
    req: StaffSuggestionRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Gợi ý nhân sự:
    - Input: Lưu lượng, doanh thu, tỷ lệ lấp đầy (bỏ trống -> backend tự tổng hợp).
    - Output: Giờ cao điểm, số lượng nhân sự, chia ca.
    """
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)

    hourly_traffic = req.hourly_traffic
    revenue = req.revenue
    occupancy_rate = req.occupancy_rate

    if hourly_traffic is None or revenue is None or occupancy_rate is None:
        dashboard_data = ParkingService(db).get_dashboard_data()
        if hourly_traffic is None:
            # Gợi ý nhân sự dựa trên Dashboard hiện tại nên dùng lưu lượng
            # hôm nay, không được âm thầm cộng dữ liệu all-time.
            traffic = ReportService(db).get_traffic_report("day")
            hourly_traffic = traffic.get("traffic_by_hour") or []
        if revenue is None:
            revenue = dashboard_data["total_revenue_today"]
        if occupancy_rate is None:
            occupancy_rate = dashboard_data["occupancy_rate_percentage"]

    schedule_plan = ai_service.suggest_staff_schedule(
        hourly_traffic=hourly_traffic,
        occupancy_rate=occupancy_rate,
        revenue=revenue,
        user_id=current_user.id
    )
    
    return {
        "message": "Tạo đề xuất nhân sự thành công", 
        "content": schedule_plan
    }


# ==========================================
# 2. CÁC API QUẢN LÝ LỊCH SỬ BÁO CÁO (CRUD)
# ==========================================
@router.get("/reports", response_model=List[ai_report_schema.AiReportResponse])
def read_ai_reports(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy danh sách lịch sử truy vấn AI của user hiện tại (mới nhất xếp trước)"""
    reports = db.query(AiReport).filter(AiReport.generated_by_id == current_user.id)\
                .order_by(desc(AiReport.created_at)).offset(skip).limit(limit).all()
    return reports

@router.get("/reports/{id}", response_model=ai_report_schema.AiReportResponse)
def read_ai_report(
    id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy chi tiết một bản ghi báo cáo AI (bảo mật: chỉ truy xuất được báo cáo của chính mình)"""
    report = db.query(AiReport).filter(
        AiReport.id == id,
        AiReport.generated_by_id == current_user.id
    ).first()
    
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo cáo AI")
    return report

@router.delete("/reports/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_report(
    id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Xóa một bản ghi lịch sử AI"""
    report = db.query(AiReport).filter(
        AiReport.id == id,
        AiReport.generated_by_id == current_user.id
    ).first()
    
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy báo cáo AI để xóa")
    
    db.delete(report)
    db.commit()
    return None
