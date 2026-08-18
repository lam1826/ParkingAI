from sqlalchemy.orm import Session
from sqlalchemy import select
from models.vehicle import Vehicle 
from schemas import vehicle as vehicle_schema

def get_vehicle(db: Session, vehicle_id: int) -> Vehicle | None:
    stmt = select(Vehicle).where(Vehicle.id == vehicle_id)
    return db.execute(stmt).scalar_one_or_none()

def get_vehicle_by_license_plate(db: Session, license_plate: str) -> Vehicle | None:
    stmt = select(Vehicle).where(Vehicle.license_plate == license_plate)
    return db.execute(stmt).scalar_one_or_none()

def get_vehicles(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(Vehicle).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_vehicle(db: Session, vehicle_in: vehicle_schema.VehicleCreate) -> Vehicle:
    db_vehicle = Vehicle(**vehicle_in.model_dump())
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

def update_vehicle(db: Session, db_vehicle: Vehicle, vehicle_in: vehicle_schema.VehicleUpdate) -> Vehicle:
    update_data = vehicle_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_vehicle, field, value)
    
    db.add(db_vehicle)
    db.commit()
    db.refresh(db_vehicle)
    return db_vehicle

def delete_vehicle(db: Session, db_vehicle: Vehicle) -> Vehicle:
    db.delete(db_vehicle)
    db.commit()
    return db_vehicle