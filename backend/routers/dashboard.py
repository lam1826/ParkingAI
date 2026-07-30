from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.dashboard import DashboardResponse
from services.parking_service import ParkingService
from services.auth_service import get_current_user
from models.user import User
from schemas.dashboard import AIInsightResponse



router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)

@router.get(
    "",
    response_model=DashboardResponse,
    status_code=status.HTTP_200_OK,
    summary="Lấy thông tin tổng quan hệ thống bãi đỗ xe"
)
def get_dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Trả về các chỉ số thống kê quan trọng cho Dashboard:
    - Tổng số xe và doanh thu trong ngày.
    - Trạng thái xe đang ở trong bãi và đã rời bãi.
    - Tỷ lệ lấp đầy của toàn bộ bãi đỗ.
    - Top 5 khung giờ có lượng xe check-in đông nhất.
    """
    service = ParkingService(db)
    return service.get_dashboard_data()


@router.get(
    "/ai-insight",
    response_model=AIInsightResponse,
    status_code=status.HTTP_200_OK,
    summary="Lấy gợi ý thông minh (AI Insight) dựa trên dữ liệu bãi đỗ hiện tại"
)
def get_ai_insight(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Phân tích tình trạng lấp đầy hiện tại và trả về một gợi ý ngắn gọn cho nhân viên.
    """
    service = ParkingService(db)
    return service.get_ai_insight_data()