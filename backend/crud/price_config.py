from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from models.price_config import PriceConfig 
from schemas import price_config as price_config_schema

def get_price_config(db: Session, config_id: int) -> PriceConfig | None:
    stmt = select(PriceConfig).where(PriceConfig.id == config_id)
    return db.execute(stmt).scalar_one_or_none()

def get_active_price_by_vehicle_type(db: Session, vehicle_type_id: int) -> PriceConfig | None:
    """Lấy cấu hình giá đang được áp dụng (active) cho một loại xe cụ thể"""
    stmt = select(PriceConfig).where(
        and_(
            PriceConfig.vehicle_type_id == vehicle_type_id,
            PriceConfig.is_active == True
        )
    )
    return db.execute(stmt).scalar_one_or_none()

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