from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import price_config as price_config_schema
from crud import price_config as crud_price_config

router = APIRouter()

@router.get("", response_model=List[price_config_schema.PriceConfigResponse])
def read_price_configs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lấy danh sách cấu hình giá"""
    return crud_price_config.get_price_configs(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=price_config_schema.PriceConfigResponse)
def read_price_config(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một cấu hình giá"""
    db_config = crud_price_config.get_price_config(db, config_id=id)
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price config not found")
    return db_config

@router.post("", response_model=price_config_schema.PriceConfigResponse, status_code=status.HTTP_201_CREATED)
def create_price_config(config_in: price_config_schema.PriceConfigCreate, db: Session = Depends(get_db)):
    """Tạo cấu hình giá mới"""
    # Chỉ cho phép tồn tại 1 bảng giá active cho mỗi loại xe tại một thời điểm
    if config_in.is_active:
        active_config = crud_price_config.get_active_price_by_vehicle_type(db, vehicle_type_id=config_in.vehicle_type_id)
        if active_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="There is already an active price configuration for this vehicle type. Please deactivate it first."
            )
    
    return crud_price_config.create_price_config(db=db, config_in=config_in)

@router.put("/{id}", response_model=price_config_schema.PriceConfigResponse)
def update_price_config(id: int, config_in: price_config_schema.PriceConfigUpdate, db: Session = Depends(get_db)):
    """Cập nhật cấu hình giá (thay đổi giá hoặc trạng thái active)"""
    db_config = crud_price_config.get_price_config(db, config_id=id)
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price config not found")
    
    # Validation như lúc POST nếu đổi trạng thái thành active
    if config_in.is_active is True and config_in.is_active != db_config.is_active:
        active_config = crud_price_config.get_active_price_by_vehicle_type(
            db, 
            vehicle_type_id=config_in.vehicle_type_id if config_in.vehicle_type_id else db_config.vehicle_type_id
        )
        if active_config and active_config.id != id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Another active price configuration exists for this vehicle type."
            )
            
    return crud_price_config.update_price_config(db=db, db_config=db_config, config_in=config_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price_config(id: int, db: Session = Depends(get_db)):
    """Xóa cấu hình giá"""
    db_config = crud_price_config.get_price_config(db, config_id=id)
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price config not found")
    
    crud_price_config.delete_price_config(db=db, db_config=db_config)
    return None