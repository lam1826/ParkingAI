from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Dict, Any
from datetime import date
from pydantic import BaseModel, Field
import traceback  # <--- BỔ SUNG ĐỂ IN CHI TIẾT LỖI

from database import get_db
from core.config import settings
from schemas import ai_report as ai_report_schema
from services.ai_service import AIService
from models.ai_report import AiReport

# IMPORT ĐÚNG: Lấy hàm get_current_user độc lập từ services.auth_service
from services.auth_service import get_current_user
from models.user import User

router = APIRouter(prefix="/ai", tags=["AI Analytics"])

# ==========================================
# SCHEMAS DÀNH RIÊNG CHO REQUEST BODY
# ==========================================
class DailyReportRequest(BaseModel):
    target_date: date
    parking_stats: Dict[str, Any]

class WeeklyReportRequest(BaseModel):
    start_date: date
    end_date: date
    weekly_data: List[Dict[str, Any]]

class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Câu hỏi của người dùng")
    parking_stats: Dict[str, Any]

class DashboardQuestionRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="Câu hỏi của người dùng về tình trạng bãi đỗ xe",
        json_schema_extra={"example": "Hôm nay bãi đỗ xe kiếm được bao nhiêu tiền?"}
    )

# BỔ SUNG: SCHEMA CHO API GỢI Ý NHÂN SỰ
class StaffSuggestionRequest(BaseModel):
    """Input: Lưu lượng, doanh thu, tỷ lệ lấp đầy"""
    hourly_traffic: List[Dict[str, Any]] = Field(..., description="Dữ liệu lưu lượng xe ra vào theo giờ")
    revenue: float = Field(..., description="Tổng doanh thu dự kiến hoặc hiện tại")
    occupancy_rate: float = Field(..., description="Tỷ lệ lấp đầy bãi đỗ xe (VD: 0.85 cho 85%)")


# ==========================================
# 1. CÁC API SINH BÁO CÁO (SỬ DỤNG AI_SERVICE)
# ==========================================
@router.post("/daily-report")
def create_daily_report(
    req: DailyReportRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI phân tích và sinh báo cáo bãi đỗ xe theo ngày"""
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)
    report_text = ai_service.generate_daily_report(
        target_date=req.target_date,
        parking_stats=req.parking_stats,
        user_id=current_user.id
    )
    return {"message": "Tạo báo cáo thành công", "content": report_text}

@router.post("/weekly-report")
def create_weekly_report(
    req: WeeklyReportRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """AI phân tích xu hướng hoạt động tuần"""
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)
    report_text = ai_service.generate_weekly_report(
        start_date=req.start_date,
        end_date=req.end_date,
        weekly_data=req.weekly_data,
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
    try:
        ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)
        answer = ai_service.answer_question(
            question=req.question,
            parking_stats=req.parking_stats,
            user_id=current_user.id
        )
        return {"message": "Truy vấn thành công", "content": answer}
    except Exception as e:
        # <--- BỔ SUNG: In chi tiết lỗi ra Terminal và trả về HTTP 500 rõ ràng
        print("====== LỖI CRASH TẠI AI_SERVICE ======")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống AI: {str(e)}")

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
    - Input: Lưu lượng, doanh thu, tỷ lệ lấp đầy.
    - Output: Giờ cao điểm, số lượng nhân sự, chia ca.
    """
    ai_service = AIService(db, api_key=settings.GEMINI_API_KEY)
    
    schedule_plan = ai_service.suggest_staff_schedule(
        hourly_traffic=req.hourly_traffic,
        occupancy_rate=req.occupancy_rate,
        revenue=req.revenue,
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
    skip: int = 0, 
    limit: int = 100, 
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