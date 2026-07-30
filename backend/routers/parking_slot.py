from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import parking_slot as slot_schema
from crud import parking_slot as crud_slot
from crud import zone as crud_zone  # Import để kiểm tra zone_id hợp lệ

router = APIRouter()

@router.get("", response_model=List[slot_schema.ParkingSlotResponse])
def read_parking_slots(skip: int = 0, limit: int = 100, zone_id: int = None, db: Session = Depends(get_db)):
    """Lấy danh sách các vị trí đỗ xe (có hỗ trợ lọc theo zone_id)"""
    if zone_id:
        return crud_slot.get_parking_slots_by_zone(db, zone_id=zone_id, skip=skip, limit=limit)
    return crud_slot.get_parking_slots(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=slot_schema.ParkingSlotResponse)
def read_parking_slot(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một vị trí đỗ xe"""
    db_slot = crud_slot.get_parking_slot(db, slot_id=id)
    if not db_slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking Slot not found")
    return db_slot

@router.post("", response_model=slot_schema.ParkingSlotResponse, status_code=status.HTTP_201_CREATED)
def create_parking_slot(slot_in: slot_schema.ParkingSlotCreate, db: Session = Depends(get_db)):
    """Tạo vị trí đỗ xe mới"""
    # Kiểm tra xem zone_id có tồn tại không trước khi tạo slot
    db_zone = crud_zone.get_zone(db, zone_id=slot_in.zone_id)
    if not db_zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
        
    return crud_slot.create_parking_slot(db=db, slot_in=slot_in)

@router.put("/{id}", response_model=slot_schema.ParkingSlotResponse)
def update_parking_slot(id: int, slot_in: slot_schema.ParkingSlotUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin vị trí đỗ xe"""
    db_slot = crud_slot.get_parking_slot(db, slot_id=id)
    if not db_slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking Slot not found")
    
    # Nếu có cập nhật zone_id, phải kiểm tra xem zone mới có tồn tại không
    if slot_in.zone_id is not None:
        db_zone = crud_zone.get_zone(db, zone_id=slot_in.zone_id)
        if not db_zone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
            
    return crud_slot.update_parking_slot(db=db, db_slot=db_slot, slot_in=slot_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_parking_slot(id: int, db: Session = Depends(get_db)):
    """Xóa một vị trí đỗ xe"""
    db_slot = crud_slot.get_parking_slot(db, slot_id=id)
    if not db_slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking Slot not found")
    
    crud_slot.delete_parking_slot(db=db, db_slot=db_slot)
    return None