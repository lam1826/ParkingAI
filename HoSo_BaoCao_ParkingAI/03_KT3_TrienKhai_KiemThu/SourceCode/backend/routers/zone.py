from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import zone as zone_schema
from crud import zone as crud_zone
from crud import parking_slot as crud_slot

router = APIRouter()

@router.get("", response_model=List[zone_schema.ZoneResponse])
def read_zones(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lấy danh sách các khu vực đỗ xe"""
    return crud_zone.get_zones(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=zone_schema.ZoneResponse)
def read_zone(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một khu vực đỗ xe"""
    db_zone = crud_zone.get_zone(db, zone_id=id)
    if not db_zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return db_zone

@router.post("", response_model=zone_schema.ZoneResponse, status_code=status.HTTP_201_CREATED)
def create_zone(zone_in: zone_schema.ZoneCreate, db: Session = Depends(get_db)):
    """Tạo khu vực đỗ xe mới"""
    existing_zone = crud_zone.get_zone_by_name(db, name=zone_in.name)
    if existing_zone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên khu vực đã tồn tại.",
        )
    
    return crud_zone.create_zone(db=db, zone_in=zone_in)

@router.put("/{id}", response_model=zone_schema.ZoneResponse)
def update_zone(id: int, zone_in: zone_schema.ZoneUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin khu vực đỗ xe"""
    db_zone = crud_zone.get_zone(db, zone_id=id)
    if not db_zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    if zone_in.name is not None:
        conflicting_zone = crud_zone.get_zone_by_name(db, name=zone_in.name)
        if conflicting_zone is not None and conflicting_zone.id != db_zone.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tên khu vực đã tồn tại.",
            )
    if (
        zone_in.capacity is not None
        and zone_in.capacity < crud_slot.count_parking_slots_by_zone(db, db_zone.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sức chứa không được nhỏ hơn số vị trí đang tồn tại.",
        )
    if (
        zone_in.is_active is False
        and crud_slot.zone_has_occupied_or_active_slot(db, db_zone.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể ngừng khu vực khi đang có xe đang đỗ.",
        )
    
    return crud_zone.update_zone(db=db, db_zone=db_zone, zone_in=zone_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(id: int, db: Session = Depends(get_db)):
    """Xóa một khu vực đỗ xe"""
    db_zone = crud_zone.get_zone(db, zone_id=id)
    if not db_zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    if crud_slot.count_parking_slots_by_zone(db, db_zone.id) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xóa khu vực khi vẫn còn vị trí đỗ.",
        )
    
    crud_zone.delete_zone(db=db, db_zone=db_zone)
    return None
