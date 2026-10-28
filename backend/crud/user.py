from sqlalchemy.orm import Session
from sqlalchemy import func, select
from models.user import User
from schemas import user as user_schema
from services.auth_service import AuthService

def get_user(db: Session, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()

def username_taken(db: Session, username: str, *, exclude_id: int | None = None) -> bool:
    """Review 28/10/2026 R1-USERNAME: usernames are unique ignoring case.

    "CUSTOMER_DEMO" next to "customer_demo" would read as the same account in
    every list and audit row. Login stays exact; only new or changed names are
    checked, so existing case variants keep working.
    """
    stmt = select(User.id).where(func.lower(User.username) == username.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None

def get_users(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(User).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_user(db: Session, user_in: user_schema.UserCreate, *, commit: bool = True) -> User:
    # Lấy dữ liệu và loại bỏ trường password để chuyển thành password_hash
    # site_id is a lot assignment handled by the router, not a User column.
    user_data = user_in.model_dump(exclude={"site_id"})
    password = user_data.pop("password")

    # Băm mật khẩu bằng bcrypt thật (khớp với AuthService.verify_password khi login)
    user_data["password_hash"] = AuthService.get_password_hash(password)

    db_user = User(**user_data)
    db.add(db_user)
    if commit:
        db.commit()
        db.refresh(db_user)
    else:
        # Account and its site membership must be committed atomically.
        db.flush()
    return db_user

def update_user(db: Session, db_user: User, user_in: user_schema.UserUpdate) -> User:
    update_data = user_in.model_dump(exclude_unset=True)
    
    # Nếu có update mật khẩu thì xử lý băm mật khẩu
    if update_data.get("password"):
        password = update_data.pop("password")
        update_data["password_hash"] = AuthService.get_password_hash(password)
    else:
        update_data.pop("password", None)
    if update_data.get("is_active") is False and db_user.is_active:
        # Review 28/10/2026 R2-09: a deactivation ends every issued session for
        # good; re-activating the account later does not revive those tokens.
        update_data["password_hash"] = AuthService.revoke_sessions(
            update_data.get("password_hash", db_user.password_hash))
        
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, db_user: User) -> User:
    db.delete(db_user)
    db.commit()
    return db_user
