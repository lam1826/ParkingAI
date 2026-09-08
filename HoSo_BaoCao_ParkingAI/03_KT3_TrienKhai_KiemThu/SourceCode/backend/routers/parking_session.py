from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import parking_session as session_schema
from crud import parking_session as crud_session
from services.auth_service import RoleChecker, get_current_user
from services.checkout_service import CheckoutService
from schemas.checkout import CheckoutQuoteResponse
from models.user import User
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from expansion.site_models import ParkingSite

router = APIRouter()


@router.get("/tickets/resolve")
def resolve_parking_ticket(token: str = Query(min_length=1, max_length=128), db: Session = Depends(get_db)):
    from services.ticket_service import resolve_ticket, get_ticket
    return get_ticket(db, resolve_ticket(token))


@router.get("/{id}/ticket")
def read_parking_ticket(id: str, db: Session = Depends(get_db)):
    from services.ticket_service import get_ticket
    return get_ticket(db, id)

@router.get("", response_model=List[session_schema.ParkingSessionResponse])
def read_parking_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách lịch sử các phiên đỗ xe"""
    return crud_session.get_parking_sessions(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=session_schema.ParkingSessionResponse)
def read_parking_session(id: str, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một phiên đỗ xe (id là UUID dạng chuỗi)"""
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")
    return db_session

@router.post("/check-in", response_model=session_schema.ParkingSessionResponse, status_code=status.HTTP_201_CREATED)
def check_in_vehicle(
    session_in: session_schema.ParkingSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xử lý xe vào bãi (Check-in) — có kiểm tra vị trí đỗ và chiếm chỗ."""
    # Tránh tình trạng "xe ma": Xe chưa ra khỏi bãi nhưng lại có lượt vào tiếp theo
    active_session = crud_session.get_active_session_by_vehicle(db, vehicle_id=session_in.vehicle_id)
    if active_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This vehicle is already in the parking lot with an active session."
        )

    vehicle = db.get(Vehicle, session_in.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    # A site-bound stay needs a physical slot so both entitlement and later
    # scoped history can resolve the same site. A site inferred only for fee
    # lookup would still create an unscoped session and bypass slot capacity.
    if session_in.parking_slot_id is None and db.scalar(select(ParkingSite.id).limit(1)) is not None:
        raise HTTPException(
            status_code=422,
            detail="Hãy chọn vị trí đỗ để xác định đúng bãi và quyền vé tháng trước khi nhận xe.",
        )

    # Kiểm tra vị trí đỗ: tồn tại, đang hoạt động, còn trống, đúng loại xe
    slot = None
    if session_in.parking_slot_id is not None:
        slot = db.get(ParkingSlot, session_in.parking_slot_id)
        if not slot or not slot.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking slot not found")
        if slot.is_occupied:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parking slot is already occupied")
        if slot.vehicle_type_id != vehicle.vehicle_type_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parking slot does not support this vehicle type"
            )
    # Sample đúng một timestamp cho admission, entitlement và session. Giá
    # được kiểm tra trước slot claim để lỗi cấu hình không để lại side effect.
    check_in_time = crud_session.server_now()
    try:
        monthly_pass_id = crud_session.resolve_check_in_monthly_pass_id(
            db,
            vehicle_id=vehicle.id,
            vehicle_type_id=vehicle.vehicle_type_id,
            check_in_time=check_in_time,
            site_id=slot.zone.site_id if slot else None,
        )
        monthly_coverage_end = crud_session.resolve_check_in_monthly_coverage_end(
            db, monthly_pass_id=monthly_pass_id, check_in_time=check_in_time,
            site_id=slot.zone.site_id if slot else None,
        )
    except crud_session.MissingEffectiveCheckInPriceError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Loại xe chưa có bảng giá đang áp dụng cho ngày check-in. "
                "Hãy cấu hình bảng giá trước khi nhận xe."
            ),
        )

    if slot is not None:
        # Claim NGUYÊN TỬ thay cho gán ORM: hai request đồng thời cùng vượt
        # qua các kiểm tra đọc ở trên thì chỉ một UPDATE có điều kiện thành
        # công; request thua nhận 409, không ghi đè slot.
        if not crud_session.claim_parking_slot(
            db,
            slot.id,
            expected_zone_id=slot.zone_id,
            expected_vehicle_type_id=vehicle.vehicle_type_id,
            expected_site_id=slot.zone.site_id,
            vehicle_id=vehicle.id,
            check_in_time=check_in_time,
        ):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vị trí đỗ vừa được xe khác sử dụng. Vui lòng chọn vị trí khác."
            )

    try:
        # Claim slot + INSERT session nằm cùng transaction; commit trong CRUD
        # là điểm cùng-thành-công của cả hai thao tác.
        return crud_session.create_parking_session(
            db=db,
            session_in=session_in,
            staff_in_id=current_user.id,
            check_in_time=check_in_time,
            monthly_pass_id=monthly_pass_id,
            monthly_coverage_end=monthly_coverage_end,
        )
    except DBAPIError as exc:
        db.rollback()  # trả lại slot vừa claim trong cùng transaction
        conflict_message = crud_session.map_check_in_integrity_error(exc)
        if conflict_message is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi hệ thống khi ghi phiên gửi xe."
        )

@router.get("/{id}/checkout-quote", response_model=CheckoutQuoteResponse)
def read_checkout_quote(
    id: str, response: Response, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Read the current fee without recording collection or releasing a space."""
    response.headers["Cache-Control"] = "no-store"
    return CheckoutService(db).quote(id, current_user.id)


@router.put("/{id}/check-out", response_model=session_schema.ParkingSessionResponse)
def check_out_vehicle(
    id: str,
    session_in: session_schema.CheckOutBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete this exact session only after confirming its signed fee quote."""
    return CheckoutService(db).confirm(session_in, current_user.id, session_id=id)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(RoleChecker("admin"))])
def delete_parking_session(id: str, db: Session = Depends(get_db)):
    """Xóa phiên đỗ xe (Chỉ dành cho admin xử lý sự cố dữ liệu)"""
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")

    from models.payment import Payment
    if db.query(Payment.id).filter(Payment.source_type == "parking_session", Payment.source_id == id).first():
        raise HTTPException(409, "Phiên đã có chứng từ thu tiền nên không thể xóa. Hãy dùng nghiệp vụ hoàn tiền.")

    # Nếu phiên vẫn đang active thì trả lại chỗ đỗ trước khi xóa
    if db_session.status == "active" and db_session.parking_slot_id is not None:
        slot = db.get(ParkingSlot, db_session.parking_slot_id)
        if slot:
            slot.is_occupied = False

    crud_session.delete_parking_session(db=db, db_session=db_session)
    return None
