from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import vehicle as vehicle_schema
from crud import vehicle as crud_vehicle
# Nếu cần validate khóa ngoại chặt chẽ, bạn có thể import thêm crud_customer và crud_vehicle_type

router = APIRouter()

@router.get("", response_model=List[vehicle_schema.VehicleResponse])
def read_vehicles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lấy danh sách phương tiện"""
    return crud_vehicle.get_vehicles(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=vehicle_schema.VehicleResponse)
def read_vehicle(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một phương tiện"""
    db_vehicle = crud_vehicle.get_vehicle(db, vehicle_id=id)
    if not db_vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return db_vehicle

@router.post("", response_model=vehicle_schema.VehicleResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle(vehicle_in: vehicle_schema.VehicleCreate, db: Session = Depends(get_db)):
    """Đăng ký phương tiện mới"""
    # Kiểm tra biển số xe đã tồn tại chưa
    existing_vehicle = crud_vehicle.get_vehicle_by_license_plate(db, license_plate=vehicle_in.license_plate)
    if existing_vehicle:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="License plate already registered")
    
    return crud_vehicle.create_vehicle(db=db, vehicle_in=vehicle_in)

@router.put("/{id}", response_model=vehicle_schema.VehicleResponse)
def update_vehicle(id: int, vehicle_in: vehicle_schema.VehicleUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin phương tiện"""
    db_vehicle = crud_vehicle.get_vehicle(db, vehicle_id=id)
    if not db_vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    
    # Kiểm tra nếu đổi biển số thì biển mới có bị trùng với xe khác không
    if vehicle_in.license_plate and vehicle_in.license_plate != db_vehicle.license_plate:
        existing_vehicle = crud_vehicle.get_vehicle_by_license_plate(db, license_plate=vehicle_in.license_plate)
        if existing_vehicle:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="License plate already in use")
            
    return crud_vehicle.update_vehicle(db=db, db_vehicle=db_vehicle, vehicle_in=vehicle_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(id: int, db: Session = Depends(get_db)):
    """Xóa một phương tiện"""
    db_vehicle = crud_vehicle.get_vehicle(db, vehicle_id=id)
    if not db_vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    
    crud_vehicle.delete_vehicle(db=db, db_vehicle=db_vehicle)
    return None