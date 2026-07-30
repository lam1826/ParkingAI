from typing import Annotated, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

# Import cấu hình database, service và schemas
from database import get_db
from services.parking_service import ParkingService
from schemas.parking import (
    CheckInRequest,
    CheckOutRequest,
    CheckOutResponse,
    AvailableSlotsOverviewResponse,
    PaginatedParkingSearchResponse,
)

# Dependency lấy user hiện tại
from services.auth_service import get_current_user
from models.user import User

router = APIRouter(
    prefix="/parking",
    tags=["Parking Management"]
)


@router.post(
    "/check-in",
    status_code=status.HTTP_201_CREATED,
    summary="Check-in phương tiện vào bãi"
)
def check_in_endpoint(
    body: CheckInRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Xử lý phương tiện vào bãi đỗ:
    - Kiểm tra loại xe và tình trạng xe.
    - Cấp phát chỗ đỗ trống tự động.
    - Tạo phiên gửi xe (ParkingSession).
    """
    service = ParkingService(db)
    return service.check_in(
        license_plate=body.license_plate,
        vehicle_type_id=body.vehicle_type_id,
        zone_id=body.zone_id,
        staff_id=current_user.id
    )


@router.post(
    "/check-out",
    response_model=CheckOutResponse,
    status_code=status.HTTP_200_OK,
    summary="Thực hiện check-out cho phương tiện rời bãi"
)
def check_out_endpoint(
    body: CheckOutRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    API xử lý xe rời bãi đỗ:
    - Nhận biển số xe đã được validate qua Pydantic Schema.
    - Tìm phiên đỗ xe hợp lệ đang hoạt động.
    - Tính toán chi phí (Miễn phí nếu có vé tháng hợp lệ).
    - Cập nhật trạng thái hóa đơn và giải phóng chỗ đỗ.
    """
    service = ParkingService(db)
    return service.check_out(license_plate=body.license_plate, staff_id=current_user.id)


@router.get(
    "/statistics",
    status_code=status.HTTP_200_OK,
    summary="Thống kê hoạt động bãi đỗ trong ngày"
)
def get_statistics_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Lấy báo cáo tổng quan trong ngày:
    - Tổng lượt xe check-in.
    - Tổng doanh thu.
    - Số lượng chỗ trống và đang sử dụng.
    - Khung giờ cao điểm có lượng xe vào đông nhất.
    """
    service = ParkingService(db)
    return service.get_parking_statistics()


@router.get(
    "/available-slots",
    response_model=AvailableSlotsOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Lấy danh sách và thống kê chỗ đỗ trống theo khu vực"
)
def get_available_slots_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Trả về thông tin chi tiết:
    - Tổng số chỗ đỗ toàn hệ thống.
    - Số chỗ đang sử dụng.
    - Số chỗ còn trống.
    - Danh sách vị trí còn trống được phân loại theo từng khu vực (Zone).
    """
    service = ParkingService(db)
    return service.get_available_slots_summary()


@router.get(
    "/search",
    response_model=PaginatedParkingSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Tìm kiếm, lọc và phân trang lịch sử gửi xe"
)
def search_parking_sessions_endpoint(
    license_plate: Optional[str] = Query(
        None,
        description="Lọc theo biển số xe (tìm kiếm tương đối)"
    ),
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Lọc theo trạng thái (active, completed)"
    ),
    date_from: Optional[datetime] = Query(
        None,
        description="Lọc từ thời gian vào (ISO format: YYYY-MM-DDTHH:MM:SS)"
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Lọc đến thời gian vào (ISO format: YYYY-MM-DDTHH:MM:SS)"
    ),
    page: int = Query(
        1,
        ge=1,
        description="Số trang hiện tại (bắt đầu từ 1)"
    ),
    size: int = Query(
        10,
        ge=1,
        le=100,
        description="Số lượng bản ghi trên một trang (tối đa 100)"
    ),
    sort_by: str = Query(
        "check_in_time",
        description="Trường cần sắp xếp: check_in_time, check_out_time, parking_fee"
    ),
    sort_order: str = Query(
        "desc",
        pattern="^(asc|desc|ASC|DESC)$",
        description="Thứ tự sắp xếp: asc hoặc desc"
    ),
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[User, Depends(get_current_user)] = None
):
    """
    API tìm kiếm nâng cao lịch sử gửi xe:
    - Filter theo biển số xe.
    - Filter theo trạng thái phiên gửi xe.
    - Filter theo khoảng thời gian.
    - Sắp xếp theo thời gian vào, thời gian ra hoặc phí gửi xe.
    - Phân trang với page và size.
    """
    service = ParkingService(db)
    return service.search_sessions(
        license_plate=license_plate,
        parking_status=status_filter,
        date_from=date_from,
        date_to=date_to,
        page=page,
        size=size,
        sort_by=sort_by,
        sort_order=sort_order
    )