from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.report import TrafficReportResponse, RevenueReportResponse
from services.report_service import TrafficService, RevenueService
from services.auth_service import get_current_user
from models.user import User

router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


@router.get(
    "/traffic",
    response_model=TrafficReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Lấy báo cáo lưu lượng phương tiện theo giờ, ngày, tuần, tháng"
)
def get_traffic_report_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    API trả về dữ liệu lưu lượng xe ra vào bãi đỗ dưới định dạng JSON chuẩn:
    - Lưu lượng theo khung giờ trong ngày.
    - Lưu lượng theo từng ngày.
    - Lưu lượng theo từng tuần trong năm.
    - Lưu lượng theo từng tháng.
    """
    service = TrafficService(db)
    return service.get_traffic_report()


@router.get(
    "/revenue",
    response_model=RevenueReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Lấy báo cáo doanh thu theo ngày, tuần, tháng hoặc năm"
)
def get_revenue_report_endpoint(
    period: Literal["day", "week", "month", "year"] = Query(
        "day",
        description="Khoảng thời gian thống kê: day (ngày), week (tuần), month (tháng), year (năm)"
    ),
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None
):
    """
    API báo cáo doanh thu hệ thống bãi đỗ xe:
    - **Tổng lượt**: Số lượng xe hoàn tất quy trình gửi/trả trong khoảng thời gian chọn.
    - **Tổng doanh thu**: Tổng số tiền thu được từ phí đỗ xe.
    - **Trung bình phí**: Số tiền thu trung bình trên mỗi lượt gửi xe.
    - **Loại xe nhiều nhất**: Tên loại phương tiện chiếm tỷ trọng lượt gửi lớn nhất.
    """
    service = RevenueService(db)
    return service.get_revenue_report(filter_type=period)