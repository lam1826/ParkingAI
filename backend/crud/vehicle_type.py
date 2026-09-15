from sqlalchemy.orm import Session
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from models.vehicle_type import VehicleType
from schemas import vehicle_type as vt_schema


def lock_vehicle_type(db: Session, type_id: int, *, admission=False) -> VehicleType | None:
    """Keep admission and deactivation ordered until the caller commits.

    Admissions share a PostgreSQL lock, avoiding lock-order conflicts with
    reservation/vehicle/slot paths. Type changes take the exclusive lock.
    SQLite serializes writers via the same harmless no-op used by cash locks.
    """
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(VehicleType).where(VehicleType.id == type_id)
                   .values(id=VehicleType.id, updated_at=VehicleType.updated_at))
    return db.scalar(select(VehicleType).where(VehicleType.id == type_id)
                     .with_for_update(read=admission).execution_options(populate_existing=True))


def require_active_vehicle_type(db: Session, type_id: int) -> VehicleType:
    row = lock_vehicle_type(db, type_id, admission=True)
    if row is None or not row.is_active:
        raise HTTPException(409, "Loại xe đã ngừng sử dụng. Không thể nhận thêm xe thuộc loại này.")
    return row

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
    db_vt = lock_vehicle_type(db, db_vt.id)
    if db_vt is None:
        raise HTTPException(404, "Loại xe không còn tồn tại.")
    if update_data.get("is_active") is False:
        from models.parking_session import ParkingSession
        from models.vehicle import Vehicle
        has_stay = db.scalar(select(ParkingSession.id).join(Vehicle).where(
            Vehicle.vehicle_type_id == db_vt.id, ParkingSession.status.in_(("active", "checking_out")),
        ).limit(1))
        if has_stay:
            raise HTTPException(409, "Không thể ngừng loại xe khi vẫn còn xe đang gửi. Hãy cho xe ra trước.")
        from models.parking_slot import ParkingSlot
        from expansion.reservations import has_slot_commitment
        from crud.parking_session import server_now
        if db.scalar(select(ParkingSlot.id).where(
            ParkingSlot.vehicle_type_id == db_vt.id,
            (ParkingSlot.is_occupied.is_(True) | has_slot_commitment(ParkingSlot.id, server_now())),
        ).limit(1)) is not None:
            raise HTTPException(409, "Không thể ngừng loại xe khi vị trí còn có xe hoặc cam kết đặt chỗ.")
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
    db_vt = lock_vehicle_type(db, db_vt.id)
    if db_vt is None:
        raise HTTPException(404, "Loại xe không còn tồn tại.")
    from models.vehicle import Vehicle
    from models.parking_slot import ParkingSlot
    from models.price_config import PriceConfig
    for model in (Vehicle, ParkingSlot, PriceConfig):
        if db.scalar(select(model.id).where(model.vehicle_type_id == db_vt.id).limit(1)) is not None:
            raise HTTPException(409, "Loại xe đang được sử dụng hoặc có lịch sử. Hãy ngừng sử dụng thay vì xóa.")
    db.delete(db_vt)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return db_vt
