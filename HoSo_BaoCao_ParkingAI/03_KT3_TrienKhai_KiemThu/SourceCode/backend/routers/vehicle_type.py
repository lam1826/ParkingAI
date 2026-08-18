from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import vehicle_type as vt_schema
from crud import vehicle_type as crud_vt

router = APIRouter()

@router.get("", response_model=List[vt_schema.VehicleTypeResponse])
def read_vehicle_types(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lấy danh sách các loại xe"""
    return crud_vt.get_vehicle_types(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=vt_schema.VehicleTypeResponse)
def read_vehicle_type(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một loại xe"""
    db_vt = crud_vt.get_vehicle_type(db, vt_id=id)
    if not db_vt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle Type not found")
    return db_vt

@router.post("", response_model=vt_schema.VehicleTypeResponse, status_code=status.HTTP_201_CREATED)
def create_vehicle_type(vt_in: vt_schema.VehicleTypeCreate, db: Session = Depends(get_db)):
    """Tạo loại xe mới"""
    existing_vt = crud_vt.get_vehicle_type_by_name(db, name=vt_in.name)
    if existing_vt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vehicle Type name already exists")
    
    return crud_vt.create_vehicle_type(db=db, vt_in=vt_in)

@router.put("/{id}", response_model=vt_schema.VehicleTypeResponse)
def update_vehicle_type(id: int, vt_in: vt_schema.VehicleTypeUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin loại xe"""
    db_vt = crud_vt.get_vehicle_type(db, vt_id=id)
    if not db_vt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle Type not found")
    
    return crud_vt.update_vehicle_type(db=db, db_vt=db_vt, vt_in=vt_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle_type(id: int, db: Session = Depends(get_db)):
    """Xóa một loại xe"""
    db_vt = crud_vt.get_vehicle_type(db, vt_id=id)
    if not db_vt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle Type not found")
    
    crud_vt.delete_vehicle_type(db=db, db_vt=db_vt)
    return None