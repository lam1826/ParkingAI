from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from models.vehicle_type import VehicleType
from schemas import vehicle_type as vt_schema

def get_vehicle_type(db: Session, vt_id: int) -> VehicleType | None:
    stmt = select(VehicleType).where(VehicleType.id == vt_id)
    return db.execute(stmt).scalar_one_or_none()

def get_vehicle_type_by_name(db: Session, name: str) -> VehicleType | None:
    normalized_name = name.strip().casefold()
    stmt = (
        select(VehicleType)
        .where(func.unicode_casefold(VehicleType.name) == normalized_name)
        .order_by(VehicleType.id)
    )
    return db.execute(stmt).scalars().first()

def get_vehicle_types(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(VehicleType).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_vehicle_type(db: Session, vt_in: vt_schema.VehicleTypeCreate) -> VehicleType:
    db_vt = VehicleType(**vt_in.model_dump())
    db.add(db_vt)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_vt)
    return db_vt

def update_vehicle_type(db: Session, db_vt: VehicleType, vt_in: vt_schema.VehicleTypeUpdate) -> VehicleType:
    update_data = vt_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_vt, field, value)
    
    db.add(db_vt)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_vt)
    return db_vt

def delete_vehicle_type(db: Session, db_vt: VehicleType) -> VehicleType:
    db.delete(db_vt)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return db_vt
