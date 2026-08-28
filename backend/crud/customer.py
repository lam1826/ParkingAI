from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.vehicle import Vehicle
from schemas import customer as customer_schema

def get_customer(db: Session, customer_id: int) -> Customer | None:
    stmt = select(Customer).where(Customer.id == customer_id)
    return db.execute(stmt).scalar_one_or_none()

def get_customer_by_phone(db: Session, phone_number: str) -> Customer | None:
    # Phải dùng cùng normalization seam với unique expression index
    # `uq_customers_phone_normalized`; so sánh exact sẽ bỏ sót row legacy
    # còn khoảng trắng và chỉ rơi xuống IntegrityError chung chung.
    stmt = select(Customer).where(
        func.unicode_casefold(Customer.phone_number)
        == func.unicode_casefold(phone_number)
    )
    return db.execute(stmt).scalar_one_or_none()

def get_customers(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(Customer).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def customer_has_vehicles(db: Session, customer_id: int) -> bool:
    stmt = select(Vehicle.id).where(Vehicle.customer_id == customer_id).limit(1)
    return db.execute(stmt).first() is not None

def customer_has_monthly_passes(db: Session, customer_id: int) -> bool:
    stmt = (
        select(MonthlyPass.id)
        .where(MonthlyPass.customer_id == customer_id)
        .limit(1)
    )
    return db.execute(stmt).first() is not None

def create_customer(db: Session, customer_in: customer_schema.CustomerCreate) -> Customer:
    db_customer = Customer(**customer_in.model_dump())
    db.add(db_customer)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_customer)
    return db_customer

def update_customer(db: Session, db_customer: Customer, customer_in: customer_schema.CustomerUpdate) -> Customer:
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    
    db.add(db_customer)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_customer)
    return db_customer

def delete_customer(db: Session, db_customer: Customer) -> Customer:
    db.delete(db_customer)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return db_customer
