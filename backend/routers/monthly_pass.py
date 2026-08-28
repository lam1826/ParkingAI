from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import monthly_pass as monthly_pass_schema
from crud import monthly_pass as crud_monthly_pass
from models.parking_session import ParkingSession

router = APIRouter()

@router.get("", response_model=List[monthly_pass_schema.MonthlyPassResponse])
def read_monthly_passes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách tất cả vé tháng"""
    return crud_monthly_pass.get_monthly_passes(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=monthly_pass_schema.MonthlyPassResponse)
def read_monthly_pass(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một vé tháng"""
    db_pass = crud_monthly_pass.get_monthly_pass(db, pass_id=id)
    if not db_pass:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly pass not found")
    return db_pass

@router.post("", response_model=monthly_pass_schema.MonthlyPassResponse, status_code=status.HTTP_201_CREATED)
def create_monthly_pass(pass_in: monthly_pass_schema.MonthlyPassCreate, db: Session = Depends(get_db)):
    """Đăng ký vé tháng mới"""
    # Mã thẻ NFC/RFID phải duy nhất toàn hệ thống (DB còn có unique index backstop)
    if crud_monthly_pass.get_pass_by_code(db, pass_code=pass_in.pass_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã thẻ này đã được sử dụng cho một vé tháng khác.",
        )

    # Mỗi xe có thể đặt nhiều vé active nếu các khoảng thời gian
    # rời nhau, nhưng không được giao nhau (kể cả chạm ngày biên).
    overlapping_pass = None
    if pass_in.is_active:
        overlapping_pass = crud_monthly_pass.get_overlapping_active_pass_by_vehicle(
            db,
            vehicle_id=pass_in.vehicle_id,
            start_date=pass_in.start_date,
            end_date=pass_in.end_date,
        )
    if overlapping_pass:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Khoảng hiệu lực chồng lấn với vé tháng active "
                f"ID {overlapping_pass.id} của phương tiện này."
            ),
        )

    return crud_monthly_pass.create_monthly_pass(db=db, pass_in=pass_in)

@router.put("/{id}", response_model=monthly_pass_schema.MonthlyPassResponse)
def update_monthly_pass(id: int, pass_in: monthly_pass_schema.MonthlyPassUpdate, db: Session = Depends(get_db)):
    """Gia hạn hoặc cập nhật trạng thái vé tháng"""
    db_pass = crud_monthly_pass.get_monthly_pass(db, pass_id=id)
    if not db_pass:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly pass not found")

    # Validate khoảng ngày SAU KHI merge với bản ghi hiện có: PUT một phần
    # (chỉ start_date hoặc chỉ end_date) không được tạo ra end_date < start_date.
    # Chặn tại đây, trước khi gán vào ORM — dữ liệu sai không bao giờ được commit.
    update_data = pass_in.model_dump(exclude_unset=True)
    immutable_fields = {
        "customer_id",
        "vehicle_id",
        "pass_code",
        "price",
        "start_date",
        "end_date",
    }
    changed_history_fields = [
        field
        for field in immutable_fields.intersection(update_data)
        if update_data[field] != getattr(db_pass, field)
    ]
    if changed_history_fields and db.query(ParkingSession.id).filter(
        ParkingSession.monthly_pass_id == id
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Vé tháng đã được dùng trong lịch sử gửi xe; chỉ được thay "
                "đổi trạng thái hoạt động, không được sửa dữ liệu chứng từ."
            ),
        )
    merged_start = update_data.get("start_date", db_pass.start_date)
    merged_end = update_data.get("end_date", db_pass.end_date)
    if merged_end < merged_start:
        raise HTTPException(
            status_code=422,
            detail="Ngày hết hạn phải từ ngày bắt đầu trở đi (sau khi ghép với dữ liệu hiện có).",
        )

    # Mã thẻ mới (nếu đổi) không được trùng với vé khác
    if "pass_code" in update_data:
        duplicated = crud_monthly_pass.get_pass_by_code(
            db, pass_code=update_data["pass_code"], exclude_pass_id=db_pass.id
        )
        if duplicated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mã thẻ này đã được sử dụng cho một vé tháng khác.",
            )

    # Chặn việc bật lại/gia hạn/đổi xe tạo ra hai vé active
    # chồng khoảng. Tất cả giá trị đều lấy SAU KHI merge payload partial
    # với record hiện có; exclude chính record đang sửa.
    will_be_active = update_data.get("is_active", db_pass.is_active)
    merged_vehicle_id = update_data.get("vehicle_id", db_pass.vehicle_id)
    if will_be_active:
        overlapping_pass = crud_monthly_pass.get_overlapping_active_pass_by_vehicle(
            db,
            vehicle_id=merged_vehicle_id,
            start_date=merged_start,
            end_date=merged_end,
            exclude_pass_id=db_pass.id,
        )
        if overlapping_pass:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Khoảng hiệu lực chồng lấn với vé tháng active "
                    f"ID {overlapping_pass.id} của phương tiện này."
                ),
            )

    return crud_monthly_pass.update_monthly_pass(db=db, db_pass=db_pass, pass_in=pass_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monthly_pass(id: int, db: Session = Depends(get_db)):
    """Xóa vé tháng"""
    db_pass = crud_monthly_pass.get_monthly_pass(db, pass_id=id)
    if not db_pass:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly pass not found")
    if db.query(ParkingSession.id).filter(ParkingSession.monthly_pass_id == id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Vé tháng đã được sử dụng trong lịch sử gửi xe nên không thể xóa. "
                "Hãy chuyển vé sang trạng thái ngừng hoạt động."
            ),
        )
    
    crud_monthly_pass.delete_monthly_pass(db=db, db_pass=db_pass)
    return None
