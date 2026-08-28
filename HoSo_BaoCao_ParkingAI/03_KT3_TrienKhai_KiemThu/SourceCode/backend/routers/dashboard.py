from typing import Annotated, List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.dashboard import DashboardResponse
from services.parking_service import ParkingService
from services.auth_service import RoleChecker, get_current_user
from models.user import User
from schemas.dashboard import AIInsightResponse, RecentSessionItem, RevenueChartItem



router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    dependencies=[Depends(RoleChecker("staff"))],
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
    summary="Lấy gợi ý vận hành theo quy tắc từ dữ liệu bãi đỗ hiện tại"
)
def get_ai_insight(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Tổng hợp tình trạng lấp đầy hiện tại và trả về gợi ý
    vận hành theo quy tắc; endpoint này không gọi AI provider.
    """
    service = ParkingService(db)
    return service.get_ai_insight_data()


@router.get(
    "/recent-sessions",
    response_model=List[RecentSessionItem],
    status_code=status.HTTP_200_OK,
    summary="Lấy danh sách các phiên gửi xe gần đây nhất"
)
def get_recent_sessions(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = 10,
):
    """Trả về danh sách phiên gửi xe gần đây nhất (kèm biển số, loại xe) cho bảng Dashboard."""
    service = ParkingService(db)
    return service.get_recent_sessions(limit=limit)


@router.get(
    "/revenue-chart",
    response_model=List[RevenueChartItem],
    status_code=status.HTTP_200_OK,
    summary="Lấy doanh thu theo từng ngày trong 7 ngày gần nhất"
)
def get_revenue_chart(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Trả về doanh thu từng ngày trong 7 ngày gần nhất để vẽ biểu đồ trên Dashboard."""
    service = ParkingService(db)
    return service.get_revenue_last_7_days()
