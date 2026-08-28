from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from models.parking_session import ParkingSession
from models.price_config import PriceConfig 
from models.vehicle import Vehicle
from schemas import price_config as price_config_schema

def get_price_config(db: Session, config_id: int) -> PriceConfig | None:
    stmt = select(PriceConfig).where(PriceConfig.id == config_id)
    return db.execute(stmt).scalar_one_or_none()

def get_active_price_by_vehicle_type(
    db: Session, vehicle_type_id: int, exclude_id: int | None = None
) -> PriceConfig | None:
    """Tìm một bảng giá active của loại xe (mới nhất trước) để kiểm tra xung đột.

    Dùng .first() với thứ tự xác định thay vì scalar_one_or_none(): nếu dữ liệu
    đã hỏng sẵn (nhiều bản ghi active cùng loại xe) thì sự tồn tại của bất kỳ
    bản ghi nào cũng đủ chứng minh xung đột — không được ném MultipleResultsFound
    làm POST/PUT trả 500. exclude_id loại chính bản ghi đang update khỏi kết quả."""
    stmt = (
        select(PriceConfig)
        .where(
            and_(
                PriceConfig.vehicle_type_id == vehicle_type_id,
                PriceConfig.is_active == True,
            )
        )
        .order_by(PriceConfig.effective_date.desc(), PriceConfig.id.desc())
    )
    if exclude_id is not None:
        stmt = stmt.where(PriceConfig.id != exclude_id)
    return db.execute(stmt).scalars().first()


def get_effective_active_price_by_vehicle_type(
    db: Session,
    vehicle_type_id: int,
    effective_on: date,
) -> PriceConfig | None:
    """Return the exact active rate the current checkout algorithm can use.

    Keeping this lookup shared prevents check-in admission and checkout
    billing from drifting to different ordering/effective-date semantics.
    """
    stmt = (
        select(PriceConfig)
        .where(
            PriceConfig.vehicle_type_id == vehicle_type_id,
            PriceConfig.is_active == True,  # noqa: E712
            PriceConfig.effective_date <= effective_on,
        )
        .order_by(PriceConfig.effective_date.desc(), PriceConfig.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def has_active_session_for_vehicle_type(
    db: Session,
    vehicle_type_id: int,
) -> bool:
    """Whether this vehicle type has any stay still in progress.

    Monthly-pass stays also lock the fallback rate: if the pass expires before
    exit, checkout must still use the rate contract proven at entry.
    """
    stmt = (
        select(ParkingSession.id)
        .join(Vehicle, ParkingSession.vehicle_id == Vehicle.id)
        .where(
            Vehicle.vehicle_type_id == vehicle_type_id,
            ParkingSession.status == "active",
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None

def get_price_configs(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(PriceConfig).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_price_config(db: Session, config_in: price_config_schema.PriceConfigCreate) -> PriceConfig:
    db_config = PriceConfig(**config_in.model_dump())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

def update_price_config(db: Session, db_config: PriceConfig, config_in: price_config_schema.PriceConfigUpdate) -> PriceConfig:
    update_data = config_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_config, field, value)
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

def delete_price_config(db: Session, db_config: PriceConfig) -> PriceConfig:
    db.delete(db_config)
    db.commit()
    return db_config
