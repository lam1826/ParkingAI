from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from database import get_db
from schemas import role as role_schema
from crud import role as crud_role
from services.auth_service import RoleChecker
from core.roles import CANONICAL_ROLE_NAMES

router = APIRouter(
    # prefix="/roles",
    tags=["Roles"]
)

@router.get("", response_model=List[role_schema.RoleResponse])
def read_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Lấy danh sách các vai trò"""
    roles = crud_role.get_roles(db, skip=skip, limit=limit)
    return roles

@router.get("/{id}", response_model=role_schema.RoleResponse)
def read_role(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một vai trò theo ID"""
    db_role = crud_role.get_role(db, role_id=id)
    if not db_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return db_role

@router.post(
    "",
    response_model=role_schema.RoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RoleChecker("admin"))],
)
def create_role(role_in: role_schema.RoleCreate, db: Session = Depends(get_db)):
    """Khôi phục một vai trò chuẩn bị thiếu; không tạo role tùy ý."""
    if crud_role.get_role_by_name(db, role_in.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vai trò hệ thống đã tồn tại.",
        )
    try:
        return crud_role.create_role(db=db, role_in=role_in)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vai trò hệ thống đã tồn tại.",
        )

@router.put(
    "/{id}",
    response_model=role_schema.RoleResponse,
    dependencies=[Depends(RoleChecker("admin"))],
)
def update_role(id: int, role_in: role_schema.RoleUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin vai trò"""
    db_role = crud_role.get_role(db, role_id=id)
    if not db_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role_in.name is not None and role_in.name != db_role.name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể đổi tên vai trò hệ thống vì tên này là một phần của contract phân quyền.",
        )
    
    return crud_role.update_role(db=db, db_role=db_role, role_in=role_in)

@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(RoleChecker("admin"))],
)
def delete_role(id: int, db: Session = Depends(get_db)):
    """Xóa một vai trò"""
    db_role = crud_role.get_role(db, role_id=id)
    if not db_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if db_role.name in CANONICAL_ROLE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xóa vai trò hệ thống.",
        )
    
    crud_role.delete_role(db=db, db_role=db_role)
    return None
