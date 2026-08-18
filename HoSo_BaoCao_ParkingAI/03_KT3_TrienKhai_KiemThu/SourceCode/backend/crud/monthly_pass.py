from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import date
from models.monthly_pass import MonthlyPass 
from schemas import monthly_pass as monthly_pass_schema

def get_monthly_pass(db: Session, pass_id: int) -> MonthlyPass | None:
    stmt = select(MonthlyPass).where(MonthlyPass.id == pass_id)
    return db.execute(stmt).scalar_one_or_none()

def get_active_pass_by_vehicle(
    db: Session, vehicle_id: int, exclude_pass_id: int | None = None
) -> MonthlyPass | None:
    """Kiểm tra xe có vé tháng hợp lệ (đã bắt đầu, còn hạn và đang active) không.

    exclude_pass_id: bỏ qua chính vé đang được cập nhật (dùng khi PUT).
    """
    today = date.today()
    stmt = select(MonthlyPass).where(
        and_(
            MonthlyPass.vehicle_id == vehicle_id,
            MonthlyPass.is_active == True,
            MonthlyPass.start_date <= today,
            MonthlyPass.end_date >= today
        )
    )
    if exclude_pass_id is not None:
        stmt = stmt.where(MonthlyPass.id != exclude_pass_id)
    return db.execute(stmt).scalars().first()

def get_monthly_passes(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(MonthlyPass).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_monthly_pass(db: Session, pass_in: monthly_pass_schema.MonthlyPassCreate) -> MonthlyPass:
    db_pass = MonthlyPass(**pass_in.model_dump())
    db.add(db_pass)
    db.commit()
    db.refresh(db_pass)
    return db_pass

def update_monthly_pass(db: Session, db_pass: MonthlyPass, pass_in: monthly_pass_schema.MonthlyPassUpdate) -> MonthlyPass:
    update_data = pass_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_pass, field, value)
    
    db.add(db_pass)
    db.commit()
    db.refresh(db_pass)
    return db_pass

def delete_monthly_pass(db: Session, db_pass: MonthlyPass) -> MonthlyPass:
    db.delete(db_pass)
    db.commit()
    return db_pass