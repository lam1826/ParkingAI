from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from schemas import parking_slot as slot_schema

def get_parking_slot(db: Session, slot_id: int) -> ParkingSlot | None:
    stmt = select(ParkingSlot).where(ParkingSlot.id == slot_id)
    return db.execute(stmt).scalar_one_or_none()


def get_parking_slot_by_name(db: Session, slot_name: str) -> ParkingSlot | None:
    normalized_name = slot_name.strip().casefold()
    stmt = (
        select(ParkingSlot)
        .where(func.unicode_casefold(ParkingSlot.slot_name) == normalized_name)
        .order_by(ParkingSlot.id)
    )
    return db.execute(stmt).scalars().first()

def get_parking_slots_by_zone(db: Session, zone_id: int, skip: int = 0, limit: int = 100):
    stmt = select(ParkingSlot).where(ParkingSlot.zone_id == zone_id).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def get_parking_slots(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(ParkingSlot).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()


def count_parking_slots_by_zone(db: Session, zone_id: int) -> int:
    stmt = select(func.count(ParkingSlot.id)).where(ParkingSlot.zone_id == zone_id)
    return int(db.execute(stmt).scalar_one())


def has_active_parking_session(db: Session, slot_id: int) -> bool:
    stmt = (
        select(ParkingSession.id)
        .where(
            ParkingSession.parking_slot_id == slot_id,
            ParkingSession.status == "active",
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def has_any_parking_session(db: Session, slot_id: int) -> bool:
    stmt = (
        select(ParkingSession.id)
        .where(ParkingSession.parking_slot_id == slot_id)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def zone_has_occupied_or_active_slot(db: Session, zone_id: int) -> bool:
    stmt = (
        select(ParkingSlot.id)
        .outerjoin(
            ParkingSession,
            and_(
                ParkingSession.parking_slot_id == ParkingSlot.id,
                ParkingSession.status == "active",
            ),
        )
        .where(
            ParkingSlot.zone_id == zone_id,
            or_(
                ParkingSlot.is_occupied == True,  # noqa: E712
                ParkingSession.id.is_not(None),
            ),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None

def create_parking_slot(db: Session, slot_in: slot_schema.ParkingSlotCreate) -> ParkingSlot:
    db_slot = ParkingSlot(**slot_in.model_dump())
    db.add(db_slot)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_slot)
    return db_slot

def update_parking_slot(db: Session, db_slot: ParkingSlot, slot_in: slot_schema.ParkingSlotUpdate) -> ParkingSlot:
    update_data = slot_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_slot, field, value)
    
    db.add(db_slot)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_slot)
    return db_slot

def delete_parking_slot(db: Session, db_slot: ParkingSlot) -> ParkingSlot:
    db.delete(db_slot)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return db_slot
