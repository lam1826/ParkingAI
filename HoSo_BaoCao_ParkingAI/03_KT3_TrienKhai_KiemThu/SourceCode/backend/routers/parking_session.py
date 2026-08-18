from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

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
        slot.is_occupied = True

    return crud_session.create_parking_session(db=db, session_in=session_in, staff_in_id=current_user.id)

@router.put("/{id}/check-out", response_model=session_schema.ParkingSessionResponse)
def check_out_vehicle(
    id: str,
    session_in: session_schema.ParkingSessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xử lý xe ra bãi (Check-out) — server tự tính phí và giải phóng vị trí.

    Phí do server tính từ bảng giá/vé tháng; giá trị parking_fee client gửi lên bị bỏ qua
    để tránh gian lận hoặc tính phí hai lần.
    """
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")

    if db_session.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This parking session has already been completed."
        )

    check_out_time = session_in.check_out_time or datetime.now()

    vehicle = db.get(Vehicle, db_session.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    service = ParkingService(db)
    fee = service.calculate_fee(
        vehicle_id=vehicle.id,
        vehicle_type_id=vehicle.vehicle_type_id,
        time_in=db_session.check_in_time,
        time_out=check_out_time,
    )

    db_session.check_out_time = check_out_time
    db_session.parking_fee = fee
    db_session.status = "completed"
    db_session.staff_out_id = current_user.id

    # Giải phóng vị trí đỗ trong cùng transaction
    if db_session.parking_slot_id is not None:
        slot = db.get(ParkingSlot, db_session.parking_slot_id)
        if slot:
            slot.is_occupied = False

    db.commit()
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
