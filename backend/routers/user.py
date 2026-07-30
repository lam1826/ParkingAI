from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from schemas import user as user_schema
from crud import user as crud_user

# Không cần khai báo prefix ở đây vì sẽ được gộp ở main.py
router = APIRouter()

@router.get("", response_model=List[user_schema.UserResponse])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lấy danh sách người dùng"""
    return crud_user.get_users(db, skip=skip, limit=limit)

@router.get("/{id}", response_model=user_schema.UserResponse)
def read_user(id: int, db: Session = Depends(get_db)):
    """Lấy thông tin chi tiết một người dùng theo ID"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user

@router.post("", response_model=user_schema.UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: user_schema.UserCreate, db: Session = Depends(get_db)):
    """Tạo người dùng mới"""
    # Kiểm tra xem username đã tồn tại chưa
    existing_user = crud_user.get_user_by_username(db, username=user_in.username)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    
    return crud_user.create_user(db=db, user_in=user_in)

@router.put("/{id}", response_model=user_schema.UserResponse)
def update_user(id: int, user_in: user_schema.UserUpdate, db: Session = Depends(get_db)):
    """Cập nhật thông tin người dùng"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return crud_user.update_user(db=db, db_user=db_user, user_in=user_in)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(id: int, db: Session = Depends(get_db)):
    """Xóa một người dùng"""
    db_user = crud_user.get_user(db, user_id=id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    crud_user.delete_user(db=db, db_user=db_user)
    return None