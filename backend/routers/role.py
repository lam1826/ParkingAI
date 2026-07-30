from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import role as role_schema
from crud import role as crud_role

router = APIRouter(
    # prefix="/roles",
    tags=["Roles"]
)

@router.get("", response_model=List[role_schema.RoleResponse])
def read_roles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
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

@router.post("", response_model=role_schema.RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(role_in: role_schema.RoleCreate, db: Session = Depends(get_db)):
    """Tạo vai trò mới"""
    # Bạn có thể thêm logic kiểm tra trùng lặp (ví dụ name) ở đây nếu cần
    return crud_role.create_role(db=db, role_in=role_in)

@router.put("/{id}", response_model=role_schema.RoleResponse)
def update_role(id: int, role_in: role_schema.RoleUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin vai trò"""
    db_role = crud_role.get_role(db, role_id=id)
    if not db_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    
    return crud_role.update_role(db=db, db_role=db_role, role_in=role_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(id: int, db: Session = Depends(get_db)):
    """Xóa một vai trò"""
    db_role = crud_role.get_role(db, role_id=id)
    if not db_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    
    crud_role.delete_role(db=db, db_role=db_role)
    return None