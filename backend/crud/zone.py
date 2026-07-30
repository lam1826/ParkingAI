from sqlalchemy.orm import Session
from sqlalchemy import select
from models.zone import Zone  # Đảm bảo bạn có class Zone trong models/
from schemas import zone as zone_schema

def get_zone(db: Session, zone_id: int) -> Zone | None:
    stmt = select(Zone).where(Zone.id == zone_id)
    return db.execute(stmt).scalar_one_or_none()

def get_zone_by_name(db: Session, name: str) -> Zone | None:
    stmt = select(Zone).where(Zone.name == name)
    return db.execute(stmt).scalar_one_or_none()

def get_zones(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(Zone).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_zone(db: Session, zone_in: zone_schema.ZoneCreate) -> Zone:
    db_zone = Zone(**zone_in.model_dump())
    db.add(db_zone)
    db.commit()
    db.refresh(db_zone)
    return db_zone

def update_zone(db: Session, db_zone: Zone, zone_in: zone_schema.ZoneUpdate) -> Zone:
    update_data = zone_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_zone, field, value)
    
    db.add(db_zone)
    db.commit()
    db.refresh(db_zone)
    return db_zone

def delete_zone(db: Session, db_zone: Zone) -> Zone:
    db.delete(db_zone)
    db.commit()
    return db_zone