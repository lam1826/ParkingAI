from typing import Annotated

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
    ParkingSearchQuery,
)

# Dependency lấy user hiện tại
from services.auth_service import RoleChecker, get_current_user
from models.user import User

router = APIRouter(
    prefix="/parking",
    tags=["Parking Management"],
    dependencies=[Depends(RoleChecker("staff"))],
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
        parking_slot_id=body.parking_slot_id,
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
    filters: Annotated[ParkingSearchQuery, Query()],
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
        license_plate=filters.license_plate,
        parking_status=filters.status_filter,
        date_from=filters.date_from,
        date_to=filters.date_to,
        zone_id=filters.zone_id,
        vehicle_type_id=filters.vehicle_type_id,
        page=filters.page,
        size=filters.size,
        sort_by=filters.sort_by,
        sort_order=filters.sort_order,
    )
