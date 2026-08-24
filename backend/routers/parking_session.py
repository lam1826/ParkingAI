from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import parking_session as session_schema
from crud import parking_session as crud_session
from services.auth_service import RoleChecker, get_current_user
from services.parking_service import ParkingService
from models.user import User
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle

router = APIRouter()

@router.get("", response_model=List[session_schema.ParkingSessionResponse])
def read_parking_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
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

    # Kiểm tra vị trí đỗ: tồn tại, đang hoạt động, còn trống, đúng loại xe
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
        # Claim NGUYÊN TỬ thay cho gán ORM: hai request đồng thời cùng vượt
        # qua các kiểm tra đọc ở trên thì chỉ một UPDATE có điều kiện thành
        # công; request thua nhận 409, không ghi đè slot.
        if not crud_session.claim_parking_slot(db, slot.id):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vị trí đỗ vừa được xe khác sử dụng. Vui lòng chọn vị trí khác."
            )

    try:
        # Claim slot + INSERT session nằm cùng transaction; commit trong CRUD
        # là điểm cùng-thành-công của cả hai thao tác.
        return crud_session.create_parking_session(db=db, session_in=session_in, staff_in_id=current_user.id)
    except IntegrityError as exc:
        db.rollback()  # trả lại slot vừa claim trong cùng transaction
        conflict_message = crud_session.map_check_in_integrity_error(exc)
        if conflict_message is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict_message)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi hệ thống khi ghi phiên gửi xe."
        )

@router.put("/{id}/check-out", response_model=session_schema.ParkingSessionResponse)
def check_out_vehicle(
    id: str,
    session_in: session_schema.CheckOutBody | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xử lý xe ra bãi (Check-out) — IDEMPOTENT trên một session xác định.

    - check_out_time, parking_fee, status, staff_out_id hoàn toàn do SERVER
      quyết định; body chứa bất kỳ field nào đều bị 422 (CheckOutBody forbid).
    - Lần đầu: claim nguyên tử active -> completed, tính phí, giải phóng slot.
    - Các lần sau (hoặc thua race): trả 200 với đúng dữ liệu đã persist,
      không tính lại phí, không lặp side effect.
    """
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")

    if db_session.status == "completed":
        # Idempotent: trả dữ liệu đã persist, không side effect nào chạy lại
        return db_session

    if db_session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Phiên gửi xe đang ở trạng thái '{db_session.status}', "
                   "không thể check-out."
        )

    vehicle = db.get(Vehicle, db_session.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    # Claim NGUYÊN TỬ trước khi tính phí: chỉ một transaction chuyển được
    # active -> completed; claim + phí + slot cùng transaction này.
    if not crud_session.claim_session_for_checkout(db, db_session.id):
        # Thua race: winner vừa hoàn tất phiên NÀY. Kết thúc transaction đọc
        # cũ rồi đọc lại chính session đó để trả kết quả idempotent.
        db.rollback()
        winner_state = crud_session.get_parking_session(db, session_id=id)
        if winner_state is not None and winner_state.status == "completed":
            return winner_state
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phiên gửi xe vừa được xử lý bởi một yêu cầu khác. "
                   "Vui lòng tải lại."
        )

    try:
        # Đồng hồ server, lấy ĐÚNG MỘT LẦN cho phí + DB + response
        check_out_time = crud_session.server_now()

        service = ParkingService(db)
        fee = service.calculate_fee(
            vehicle_id=vehicle.id,
            vehicle_type_id=vehicle.vehicle_type_id,
            time_in=db_session.check_in_time,
            time_out=check_out_time,
        )

        db_session.check_out_time = check_out_time
        db_session.parking_fee = fee
        db_session.status = "completed"  # đồng bộ ORM với UPDATE claim
        db_session.staff_out_id = current_user.id

        # Giải phóng vị trí đỗ trong cùng transaction; slot thiếu do dữ liệu
        # legacy không được làm hỏng một checkout hợp lệ.
        if db_session.parking_slot_id is not None:
            slot = db.get(ParkingSlot, db_session.parking_slot_id)
            if slot:
                slot.is_occupied = False

        db.commit()
    except HTTPException:
        # calculate_fee lỗi (thiếu bảng giá...) SAU claim -> rollback trả
        # session về active, slot giữ nguyên, có thể retry.
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lỗi hệ thống trong quá trình check-out."
        )

    db.refresh(db_session)
    return db_session

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(RoleChecker("admin"))])
def delete_parking_session(id: str, db: Session = Depends(get_db)):
    """Xóa phiên đỗ xe (Chỉ dành cho admin xử lý sự cố dữ liệu)"""
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")

    # Nếu phiên vẫn đang active thì trả lại chỗ đỗ trước khi xóa
    if db_session.status == "active" and db_session.parking_slot_id is not None:
        slot = db.get(ParkingSlot, db_session.parking_slot_id)
        if slot:
            slot.is_occupied = False

    crud_session.delete_parking_session(db=db, db_session=db_session)
    return None
