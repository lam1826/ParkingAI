from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import parking_slot as slot_schema
from crud import parking_slot as crud_slot
from crud import zone as crud_zone  # Import để kiểm tra zone_id hợp lệ
from crud import vehicle_type as crud_vehicle_type

router = APIRouter()

@router.get("", response_model=List[slot_schema.ParkingSlotResponse])
def read_parking_slots(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    zone_id: int = None,
    db: Session = Depends(get_db),
):
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
    if crud_slot.get_parking_slot_by_name(db, slot_in.slot_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mã vị trí đã tồn tại.",
        )
    # Kiểm tra xem zone_id có tồn tại không trước khi tạo slot
    db_zone = crud_zone.get_zone(db, zone_id=slot_in.zone_id)
    if not db_zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    if not crud_vehicle_type.get_vehicle_type(db, vt_id=slot_in.vehicle_type_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loại xe không tồn tại.",
        )
    if crud_slot.count_parking_slots_by_zone(db, db_zone.id) >= db_zone.capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khu vực đã đạt sức chứa tối đa.",
        )
        
    return crud_slot.create_parking_slot(db=db, slot_in=slot_in)

@router.put("/{id}", response_model=slot_schema.ParkingSlotResponse)
def update_parking_slot(id: int, slot_in: slot_schema.ParkingSlotUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin vị trí đỗ xe"""
    db_slot = crud_slot.get_parking_slot(db, slot_id=id)
    if not db_slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking Slot not found")
    if slot_in.slot_name is not None:
        conflicting_slot = crud_slot.get_parking_slot_by_name(db, slot_in.slot_name)
        if conflicting_slot is not None and conflicting_slot.id != db_slot.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Mã vị trí đã tồn tại.",
            )
    changes_operational_assignment = (
        slot_in.is_active is False
        or (slot_in.zone_id is not None and slot_in.zone_id != db_slot.zone_id)
        or (
            slot_in.vehicle_type_id is not None
            and slot_in.vehicle_type_id != db_slot.vehicle_type_id
        )
    )
    if changes_operational_assignment and (
        db_slot.is_occupied or crud_slot.has_active_parking_session(db, db_slot.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể thay đổi vị trí khi đang có xe đang đỗ.",
        )
    if (
        slot_in.zone_id is not None
        and slot_in.zone_id != db_slot.zone_id
        and crud_slot.has_any_parking_session(db, db_slot.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Không thể chuyển khu vực vì vị trí đã có lịch sử gửi xe."
            ),
        )
    
    # Nếu có cập nhật zone_id, phải kiểm tra xem zone mới có tồn tại không
    if slot_in.zone_id is not None:
        db_zone = crud_zone.get_zone(db, zone_id=slot_in.zone_id)
        if not db_zone:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
        if (
            slot_in.zone_id != db_slot.zone_id
            and crud_slot.count_parking_slots_by_zone(db, db_zone.id) >= db_zone.capacity
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Khu vực đích đã đạt sức chứa tối đa.",
            )
    if (
        slot_in.vehicle_type_id is not None
        and not crud_vehicle_type.get_vehicle_type(db, vt_id=slot_in.vehicle_type_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Loại xe không tồn tại.",
        )
            
    return crud_slot.update_parking_slot(db=db, db_slot=db_slot, slot_in=slot_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_parking_slot(id: int, db: Session = Depends(get_db)):
    """Xóa một vị trí đỗ xe"""
    db_slot = crud_slot.get_parking_slot(db, slot_id=id)
    if not db_slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parking Slot not found")
    if crud_slot.has_any_parking_session(db, db_slot.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xóa vị trí đã có lịch sử gửi xe.",
        )
    
    crud_slot.delete_parking_slot(db=db, db_slot=db_slot)
    return None
