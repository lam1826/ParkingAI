from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, text
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
from expansion.site_models import ParkingSite, SiteMembership
from expansion.site_scope import require_site_access

# Không cần khai báo prefix ở đây vì sẽ được gộp ở main.py
router = APIRouter()

_ADMIN_INVARIANT_LOCK_KEY = 7_100_421


def _managed_site(db: Session, actor: User, *, required: bool = True, lock: bool = False):
    """Resolve the single active lot without weakening the legacy boundary."""
    statement = select(ParkingSite).limit(2)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    sites = db.scalars(statement).all()
    if not sites and not required:
        return None
    if len(sites) != 1:
        raise HTTPException(409, "Cần đúng một bãi để quản lý tài khoản nhân viên.")
    if lock:
        # Hold authorization until commit if an admin revokes the membership.
        membership = db.scalar(select(SiteMembership).where(
            SiteMembership.site_id == sites[0].id, SiteMembership.user_id == actor.id,
        ).with_for_update().execution_options(populate_existing=True))
        if membership is None or membership.role != "manager":
            raise HTTPException(403, "Tài khoản không còn quyền quản lý bãi này.")
    return require_site_access(db, actor, sites[0].id, "manager")


def _lock_user(db: Session, user_id: int):
    """Recheck permissions after a row lock, including SQLite's writer lock."""
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("UPDATE users SET id = id WHERE id = :id"), {"id": user_id})
    user = db.scalar(select(User).where(User.id == user_id).with_for_update()
                     .execution_options(populate_existing=True))
    if user is not None:
        db.refresh(user, ["role"])
    return user


def _staff_members(db: Session, site_id: int):
    return select(User.id).join(Role).join(SiteMembership).where(
        Role.name == "staff", SiteMembership.site_id == site_id,
        SiteMembership.role == "staff",
    )


def _manager_visible_users(db: Session, actor: User):
    site = _managed_site(db, actor, required=False)
    allowed = User.id == actor.id
    if site is not None:
        allowed = or_(allowed, User.id.in_(_staff_members(db, site.id)))
    return select(User).where(allowed)


def _authorize_staff_update(db: Session, actor: User, target_id: int,
                            user_in: user_schema.UserUpdate):
    actor = _lock_user(db, actor.id)
    if actor is None or not actor.is_active or actor.role.name != "manager":
        raise HTTPException(403, "Tài khoản không còn quyền quản lý nhân viên.")
    site = _managed_site(db, actor, lock=True)
    target = _lock_user(db, target_id)
    if target is None:
        raise HTTPException(404, "User not found")
    membership = db.scalar(select(SiteMembership).where(
        SiteMembership.site_id == site.id, SiteMembership.user_id == target.id,
    ).with_for_update().execution_options(populate_existing=True))
    if (target.id == actor.id or target.role.name != "staff"
            or membership is None or membership.role != "staff"):
        raise HTTPException(403, "Chỉ được quản lý tài khoản nhân viên thuộc bãi của mình.")
    changes = user_in.model_dump(exclude_unset=True)
    if any(value is None for field, value in changes.items() if field != "password"):
        raise HTTPException(422, "Thông tin tài khoản được cập nhật không được để null.")
    if user_in.role_id is not None and user_in.role_id != target.role_id:
        raise HTTPException(403, "Quản lý không được thay đổi vai trò của nhân viên.")
    return target


def _ensure_active_admin_remains(
    db: Session,
    db_user: User,
    user_in: user_schema.UserUpdate | None = None,
) -> None:
    """Preserve one active admin through updates and deletions (user_in=None)."""
    deleting = user_in is None
    update_data = user_in.model_dump(exclude_unset=True) if user_in is not None else {}
    if not deleting and not ({"is_active", "role_id"} & update_data.keys()):
        return

    # Both routes share a database lock held until the mutation commits or the
    # request rolls back. A process-local lock cannot protect multiple workers.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _ADMIN_INVARIANT_LOCK_KEY},
        )
    elif db.get_bind().dialect.name == "sqlite":
        # SQLite ignores FOR UPDATE. A no-op write takes its database write
        # lock before reading/counting admins, including across connections.
        db.execute(text("UPDATE roles SET name = name WHERE name = 'admin'"))

    db.refresh(db_user)
    current_role_name = db.execute(
        select(Role.name).where(Role.id == db_user.role_id)
    ).scalar_one()
    next_role_id = update_data.get("role_id", db_user.role_id)
    next_role_name = db.execute(
        select(Role.name).where(Role.id == next_role_id)
    ).scalar_one()
    next_is_active = False if deleting else update_data.get("is_active", db_user.is_active)

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
            detail="Không thể xóa, vô hiệu hóa hoặc đổi vai trò của admin hoạt động cuối cùng",
        )

@router.get("", response_model=List[user_schema.UserResponse])
def read_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lấy danh sách người dùng"""
    if current_user.role.name == "admin":
        return crud_user.get_users(db, skip=skip, limit=limit)
    return db.scalars(_manager_visible_users(db, current_user).order_by(User.id).offset(skip).limit(limit)).all()

@router.get("/{id}", response_model=user_schema.UserResponse)
def read_user(id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Lấy thông tin chi tiết một người dùng theo ID"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role.name != "admin" and db.scalar(
        _manager_visible_users(db, current_user).where(User.id == id)
    ) is None:
        raise HTTPException(403, "Không có quyền xem tài khoản này.")
    return db_user

@router.post(
    "",
    response_model=user_schema.UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker("manager"))],
)
def create_user(user_in: user_schema.UserCreate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """Tạo người dùng mới"""
    # Kiểm tra xem username đã tồn tại chưa
    existing_user = crud_user.get_user_by_username(db, username=user_in.username)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tên đăng nhập đã tồn tại")
    requested_role = db.get(Role, user_in.role_id)
    if not requested_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vai trò không tồn tại")

    try:
        if current_user.role.name == "admin":
            return crud_user.create_user(db=db, user_in=user_in)
        if requested_role.name != "staff":
            raise HTTPException(403, "Quản lý chỉ được tạo tài khoản nhân viên.")
        actor = _lock_user(db, current_user.id)
        if actor is None or not actor.is_active or actor.role.name != "manager":
            raise HTTPException(403, "Tài khoản không còn quyền quản lý nhân viên.")
        site = _managed_site(db, actor, lock=True)
        created = crud_user.create_user(db=db, user_in=user_in, commit=False)
        db.add(SiteMembership(site_id=site.id, user_id=created.id, role="staff"))
        db.commit()
        db.refresh(created)
        return created
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Không thể tạo tài khoản với dữ liệu này")
    except Exception:
        db.rollback()
        raise

@router.put(
    "/{id}",
    response_model=user_schema.UserResponse,
    dependencies=[Depends(RoleChecker("manager"))],
)
def update_user(id: int, user_in: user_schema.UserUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    """Cập nhật thông tin người dùng"""
    is_admin = current_user.role.name == "admin"
    db_user = (crud_user.get_user(db, user_id=id) if is_admin
               else _authorize_staff_update(db, current_user, id, user_in))
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user_in.username and user_in.username != db_user.username:
        existing_user = crud_user.get_user_by_username(db, username=user_in.username)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tên đăng nhập đã tồn tại")
    if user_in.role_id is not None and not db.get(Role, user_in.role_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vai trò không tồn tại")

    if is_admin:
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

    _ensure_active_admin_remains(db, db_user)

    try:
        crud_user.delete_user(db=db, db_user=db_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tài khoản đang được sử dụng và không thể xóa")
    return None
