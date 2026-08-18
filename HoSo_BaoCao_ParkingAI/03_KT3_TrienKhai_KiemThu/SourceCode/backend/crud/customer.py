from sqlalchemy.orm import Session
from sqlalchemy import select
from models.customer import Customer  # Giả định bạn đã tạo model này
from schemas import customer as customer_schema

def get_customer(db: Session, customer_id: int) -> Customer | None:
    stmt = select(Customer).where(Customer.id == customer_id)
    return db.execute(stmt).scalar_one_or_none()

def get_customer_by_phone(db: Session, phone_number: str) -> Customer | None:
    stmt = select(Customer).where(Customer.phone_number == phone_number)
    return db.execute(stmt).scalar_one_or_none()

def get_customers(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(Customer).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_customer(db: Session, customer_in: customer_schema.CustomerCreate) -> Customer:
    db_customer = Customer(**customer_in.model_dump())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def update_customer(db: Session, db_customer: Customer, customer_in: customer_schema.CustomerUpdate) -> Customer:
    update_data = customer_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)
    
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

def delete_customer(db: Session, db_customer: Customer) -> Customer:
    db.delete(db_customer)
    db.commit()
    return db_customer