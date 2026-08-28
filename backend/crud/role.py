from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from models.role import Role
from schemas import role as role_schema

def get_role(db: Session, role_id: int) -> Role | None:
    # Chuẩn SQLAlchemy 2.x sử dụng select()
    stmt = select(Role).where(Role.id == role_id)
    return db.execute(stmt).scalar_one_or_none()

def get_roles(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(Role).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()


def get_role_by_name(db: Session, name: str) -> Role | None:
    stmt = select(Role).where(Role.name == name.strip().lower())
    return db.execute(stmt).scalar_one_or_none()

def create_role(db: Session, role_in: role_schema.RoleCreate) -> Role:
    # Pydantic v2 dùng model_dump() thay cho dict()
    db_role = Role(**role_in.model_dump())
    db.add(db_role)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_role)
    return db_role

def update_role(db: Session, db_role: Role, role_in: role_schema.RoleUpdate) -> Role:
    # Chỉ lấy ra các trường thực sự được gửi lên để update
    update_data = role_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_role, field, value)
    
    db.add(db_role)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    db.refresh(db_role)
    return db_role

def delete_role(db: Session, db_role: Role) -> Role:
    db.delete(db_role)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return db_role
