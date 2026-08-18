from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import monthly_pass as monthly_pass_schema
from crud import monthly_pass as crud_monthly_pass

router = APIRouter()

@router.get("", response_model=List[monthly_pass_schema.MonthlyPassResponse])
def read_monthly_passes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
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
    # Tránh tình trạng 1 xe đăng ký 2 vé tháng cùng lúc đang còn hạn
    active_pass = crud_monthly_pass.get_active_pass_by_vehicle(db, vehicle_id=pass_in.vehicle_id)
    if active_pass:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Vehicle already has an active monthly pass"
        )
    
    return crud_monthly_pass.create_monthly_pass(db=db, pass_in=pass_in)

@router.put("/{id}", response_model=monthly_pass_schema.MonthlyPassResponse)
def update_monthly_pass(id: int, pass_in: monthly_pass_schema.MonthlyPassUpdate, db: Session = Depends(get_db)):
    """Gia hạn hoặc cập nhật trạng thái vé tháng"""
    db_pass = crud_monthly_pass.get_monthly_pass(db, pass_id=id)
    if not db_pass:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly pass not found")

    # Chặn việc bật lại/gia hạn tạo ra 2 vé active chồng lấn cho cùng một xe
    update_data = pass_in.model_dump(exclude_unset=True)
    will_be_active = update_data.get("is_active", db_pass.is_active)
    if will_be_active:
        other_active = crud_monthly_pass.get_active_pass_by_vehicle(
            db, vehicle_id=db_pass.vehicle_id, exclude_pass_id=db_pass.id
        )
        if other_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle already has another active monthly pass"
            )

    return crud_monthly_pass.update_monthly_pass(db=db, db_pass=db_pass, pass_in=pass_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monthly_pass(id: int, db: Session = Depends(get_db)):
    """Xóa vé tháng"""
    db_pass = crud_monthly_pass.get_monthly_pass(db, pass_id=id)
    if not db_pass:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monthly pass not found")
    
    crud_monthly_pass.delete_monthly_pass(db=db, db_pass=db_pass)
    return None