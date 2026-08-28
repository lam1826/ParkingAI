from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from database import get_db
from schemas import user as user_schema
from crud import user as crud_user
from models.role import Role
from models.user import User
from services.auth_service import get_current_user
from services.auth_service import RoleChecker

# Không cần khai báo prefix ở đây vì sẽ được gộp ở main.py
router = APIRouter()

_ADMIN_INVARIANT_LOCK_KEY = 7_100_421


def _ensure_active_admin_remains(
    db: Session,
    db_user: User,
    user_in: user_schema.UserUpdate,
) -> None:
    """Serialize admin demotions/deactivations and preserve one active admin."""
    update_data = user_in.model_dump(exclude_unset=True)
    if not ({"is_active", "role_id"} & update_data.keys()):
        return

    # PostgreSQL advisory locks serialize all transactions that may reduce the
    # active-admin set. SQLite is only used by the single-process test suite.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _ADMIN_INVARIANT_LOCK_KEY},
        )

    db.refresh(db_user)
    current_role_name = db.execute(
        select(Role.name).where(Role.id == db_user.role_id)
    ).scalar_one()
    next_role_id = update_data.get("role_id", db_user.role_id)
    next_role_name = db.execute(
        select(Role.name).where(Role.id == next_role_id)
    ).scalar_one()
    next_is_active = update_data.get("is_active", db_user.is_active)

    removes_active_admin = (
        db_user.is_active
        and current_role_name == "admin"
        and not (next_is_active and next_role_name == "admin")
    )
    if not removes_active_admin:
        return

    active_admin_count = db.execute(
        select(func.count(User.id))
        .join(Role, User.role_id == Role.id)
        .where(User.is_active.is_(True), Role.name == "admin")
    ).scalar_one()
    if active_admin_count <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể vô hiệu hóa hoặc đổi vai trò của admin hoạt động cuối cùng",
        )

@router.get("", response_model=List[user_schema.UserResponse])
def read_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách người dùng"""
    return crud_user.get_users(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=user_schema.UserResponse)
def read_user(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một người dùng theo ID"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user

@router.post(
    "",
    response_model=user_schema.UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker("admin"))],
)
def create_user(user_in: user_schema.UserCreate, db: Session = Depends(get_db)):
    """Tạo người dùng mới"""
    # Kiểm tra xem username đã tồn tại chưa
    existing_user = crud_user.get_user_by_username(db, username=user_in.username)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tên đăng nhập đã tồn tại")
    if not db.get(Role, user_in.role_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vai trò không tồn tại")

    try:
        return crud_user.create_user(db=db, user_in=user_in)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không thể tạo tài khoản với dữ liệu này")

@router.put(
    "/{id}",
    response_model=user_schema.UserResponse,
    dependencies=[Depends(RoleChecker("admin"))],
)
def update_user(id: int, user_in: user_schema.UserUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin người dùng"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user_in.username and user_in.username != db_user.username:
        existing_user = crud_user.get_user_by_username(db, username=user_in.username)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tên đăng nhập đã tồn tại")
    if user_in.role_id is not None and not db.get(Role, user_in.role_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vai trò không tồn tại")

    _ensure_active_admin_remains(db, db_user, user_in)

    try:
        return crud_user.update_user(db=db, db_user=db_user, user_in=user_in)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không thể cập nhật tài khoản với dữ liệu này")

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RoleChecker("admin"))],
)
def delete_user(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Xóa một người dùng"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if db_user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Không thể tự xóa tài khoản đang đăng nhập")

    try:
        crud_user.delete_user(db=db, db_user=db_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tài khoản đang được sử dụng và không thể xóa")
    return None
