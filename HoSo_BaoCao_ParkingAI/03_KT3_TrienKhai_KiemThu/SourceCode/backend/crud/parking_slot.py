from sqlalchemy.orm import Session
from sqlalchemy import select
from models.parking_slot import ParkingSlot
from schemas import parking_slot as slot_schema

def get_parking_slot(db: Session, slot_id: int) -> ParkingSlot | None:
    stmt = select(ParkingSlot).where(ParkingSlot.id == slot_id)
    return db.execute(stmt).scalar_one_or_none()

def get_parking_slots_by_zone(db: Session, zone_id: int, skip: int = 0, limit: int = 100):
    stmt = select(ParkingSlot).where(ParkingSlot.zone_id == zone_id).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def get_parking_slots(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(ParkingSlot).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_parking_slot(db: Session, slot_in: slot_schema.ParkingSlotCreate) -> ParkingSlot:
    db_slot = ParkingSlot(**slot_in.model_dump())
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    return db_slot

def update_parking_slot(db: Session, db_slot: ParkingSlot, slot_in: slot_schema.ParkingSlotUpdate) -> ParkingSlot:
    update_data = slot_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_slot, field, value)
    
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    return db_slot

def delete_parking_slot(db: Session, db_slot: ParkingSlot) -> ParkingSlot:
    db.delete(db_slot)
    db.commit()
    return db_slot