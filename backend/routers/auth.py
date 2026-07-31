from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session  # Sử dụng Session đồng bộ

from database import get_db
from models.user import User
from schemas.auth import CurrentUserResponse, TokenResponse, LoginRequest
from services.auth_service import AuthService, get_current_user

router = APIRouter(
    tags=["Authentication"]
)

@router.post("/login", response_model=TokenResponse, summary="Đăng nhập hệ thống lấy JWT Token")
def login(  # Bỏ async vì hàm service xử lý đồng bộ
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)]  # Dùng Session đồng bộ
):
    """
    Xác thực tài khoản qua JSON body (username & password), trả về Access Token.
    """
    if not body.username.strip() or not body.password.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tên đăng nhập và mật khẩu không được để trống",
        )

    auth_service = AuthService()
    # Gọi hàm đồng bộ trực tiếp không dùng await
    user = auth_service.authenticate_user(
        db=db, 
        username=body.username, 
        password=body.password
    )
    
    access_token = auth_service.create_access_token(
        user_id=user.id,
        username=user.username,
        role=str(user.role.name) if user.role else ""
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/logout", status_code=status.HTTP_200_OK, summary="Đăng xuất hệ thống")
def logout(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Đăng xuất (Client tự hủy token).
    """
    return {"message": "Đăng xuất thành công"}

@router.get("/me", response_model=CurrentUserResponse, summary="Lấy thông tin user hiện tại")
def get_me(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Trả về thông tin chi tiết của user đang sở hữu Access Token.
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": str(current_user.role.name) if current_user.role else "",
        "is_active": current_user.is_active,
    }