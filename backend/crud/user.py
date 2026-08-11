from sqlalchemy.orm import Session
from sqlalchemy import select
from models.user import User
from schemas import user as user_schema
from services.auth_service import AuthService

def get_user(db: Session, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()

def get_user_by_username(db: Session, username: str) -> User | None:
    stmt = select(User).where(User.username == username)
    return db.execute(stmt).scalar_one_or_none()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    stmt = select(User).offset(skip).limit(limit)
    return db.execute(stmt).scalars().all()

def create_user(db: Session, user_in: user_schema.UserCreate) -> User:
    # Lấy dữ liệu và loại bỏ trường password để chuyển thành password_hash
    user_data = user_in.model_dump()
    password = user_data.pop("password")

    # Băm mật khẩu bằng bcrypt thật (khớp với AuthService.verify_password khi login)
    user_data["password_hash"] = AuthService.get_password_hash(password)

    db_user = User(**user_data)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user(db: Session, db_user: User, user_in: user_schema.UserUpdate) -> User:
    update_data = user_in.model_dump(exclude_unset=True)
    
    # Nếu có update mật khẩu thì xử lý băm mật khẩu
    if update_data.get("password"):
        password = update_data.pop("password")
        update_data["password_hash"] = AuthService.get_password_hash(password)
    else:
        update_data.pop("password", None)
        
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
