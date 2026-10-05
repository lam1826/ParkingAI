from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from models.role import Role
from schemas import role as role_schema
from core.roles import ROLE_HIERARCHY

CANONICAL_ROLE_DESCRIPTIONS = {
    "admin": "Quản trị viên hệ thống",
    "manager": "Quản lý bãi đỗ xe",
    "staff": "Nhân viên vận hành bãi",
    "customer": "Khách hàng",
}


def ensure_canonical_roles(db: Session) -> list[str]:
    """Add any missing canonical role (flush only); existing rows are untouched.

    Returns the names created. The caller owns the transaction.
    """
    existing = set(db.scalars(select(Role.name)).all())
    created = []
    for name in sorted(ROLE_HIERARCHY, key=ROLE_HIERARCHY.get, reverse=True):
        if name not in existing:
            db.add(Role(name=name, description=CANONICAL_ROLE_DESCRIPTIONS[name]))
            created.append(name)
    if created:
        db.flush()
    return created

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
