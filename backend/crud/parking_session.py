from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import datetime
from models.parking_session import ParkingSession 
from schemas import parking_session as session_schema

def get_parking_session(db: Session, session_id: int) -> ParkingSession | None:
    stmt = select(ParkingSession).where(ParkingSession.id == session_id)
    return db.execute(stmt).scalar_one_or_none()

def get_active_session_by_vehicle(db: Session, vehicle_id: int) -> ParkingSession | None:
    """Kiểm tra xem xe có đang ở trong bãi không (phiên đỗ xe chưa đóng)"""
    stmt = select(ParkingSession).where(
        and_(
            ParkingSession.vehicle_id == vehicle_id,
            ParkingSession.status == "active"
        )
    )
    return db.execute(stmt).scalar_one_or_none()

def get_parking_sessions(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(ParkingSession).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_parking_session(db: Session, session_in: session_schema.ParkingSessionCreate, staff_in_id: int) -> ParkingSession:
    db_session = ParkingSession(
        vehicle_id=session_in.vehicle_id,
        parking_slot_id=session_in.parking_slot_id,
        check_in_time=session_in.check_in_time or datetime.now(),
        staff_in_id=staff_in_id,
        status="active"
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def update_parking_session(db: Session, db_session: ParkingSession, session_in: session_schema.ParkingSessionUpdate) -> ParkingSession:
    update_data = session_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_session, field, value)
    
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

def delete_parking_session(db: Session, db_session: ParkingSession) -> ParkingSession:
    db.delete(db_session)
    db.commit()
    return db_session