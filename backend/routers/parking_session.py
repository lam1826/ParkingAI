from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from database import get_db
from schemas import parking_session as session_schema
from crud import parking_session as crud_session
from services.auth_service import get_current_user
from models.user import User

router = APIRouter()

@router.get("", response_model=List[session_schema.ParkingSessionResponse])
def read_parking_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lấy danh sách lịch sử các phiên đỗ xe"""
    return crud_session.get_parking_sessions(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=session_schema.ParkingSessionResponse)
def read_parking_session(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một phiên đỗ xe"""
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
    """Xử lý xe vào bãi (Check-in)"""
    # Tránh tình trạng "xe ma": Xe chưa ra khỏi bãi nhưng lại có lượt vào tiếp theo
    active_session = crud_session.get_active_session_by_vehicle(db, vehicle_id=session_in.vehicle_id)
    if active_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="This vehicle is already in the parking lot with an active session."
        )
    
    return crud_session.create_parking_session(db=db, session_in=session_in, staff_in_id=current_user.id)

@router.put("/{id}/check-out", response_model=session_schema.ParkingSessionResponse)
def check_out_vehicle(id: int, session_in: session_schema.ParkingSessionUpdate, db: Session = Depends(get_db)):
    """Xử lý xe ra bãi (Check-out) - Cập nhật giờ ra và tính phí"""
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")
    
    if db_session.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="This parking session has already been completed."
        )

    # Tự động gán giờ ra và cập nhật trạng thái nếu client không gửi lên
    if not session_in.check_out_time:
        session_in.check_out_time = datetime.now()
    if not session_in.status:
        session_in.status = "completed"
        
    # *Lưu ý*: Sau này bạn có thể bổ sung logic chèn vào giữa bước này:
    # 1. Gọi hàm lấy MonthlyPass để kiểm tra có vé tháng không.
    # 2. Nếu không có, gọi hàm lấy PriceConfig để tính toán 'total_fee' dựa vào (check_out_time - check_in_time).
            
    return crud_session.update_parking_session(db=db, db_session=db_session, session_in=session_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_parking_session(id: int, db: Session = Depends(get_db)):
    """Xóa phiên đỗ xe (Chỉ dành cho admin xử lý sự cố dữ liệu)"""
    db_session = crud_session.get_parking_session(db, session_id=id)
    if not db_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking session not found")
    
    crud_session.delete_parking_session(db=db, db_session=db_session)
    return None