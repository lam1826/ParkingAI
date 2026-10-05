from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session  # Sử dụng Session đồng bộ

from database import get_db
from models.role import Role
from models.user import User
from schemas.auth import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UpdateProfileRequest,
)
from services.auth_service import AuthService, get_current_user
from core.auth_rate_limit import enforce_login_rate_limit, enforce_registration_rate_limit
from crud.role import ensure_canonical_roles

router = APIRouter(
    tags=["Authentication"]
)

# OAuth2-compatible router kept separately so the React JSON login endpoint and
# Swagger/OAuth2 form login can coexist without content-type ambiguity.
oauth_router = APIRouter(tags=["Authentication"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Đăng ký tài khoản",
)
def register(
    request: Request,
    body: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
):
    """Khách hàng đăng ký công khai; manager/admin cần mã do hệ thống cấp."""
    enforce_registration_rate_limit(request, db)
    auth_service = AuthService()
    auth_service.validate_registration_role(body.role, body.registration_code)

    username = body.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã tồn tại",
        )

    role = db.query(Role).filter(Role.name == body.role).first()
    if role is None:
        # A bootstrap via registration code must still leave every canonical
        # role (incl. staff) available to the Users screen.
        ensure_canonical_roles(db)
        role = db.query(Role).filter(Role.name == body.role).one()

    user = User(
        username=username,
        password_hash=auth_service.get_password_hash(body.password),
        full_name=body.full_name.strip(),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã tồn tại",
        )

    db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": role.name,
        "is_active": user.is_active,
    }

@router.post("/login", response_model=TokenResponse, summary="Đăng nhập hệ thống lấy JWT Token")
def login(  # Bỏ async vì hàm service xử lý đồng bộ
    request: Request,
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)]  # Dùng Session đồng bộ
):
    """
    Xác thực tài khoản qua JSON body (username & password), trả về Access Token.
    """
    enforce_login_rate_limit(request, db)
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
        role=str(user.role.name) if user.role else "",
        password_hash=user.password_hash,
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@oauth_router.post("/login", response_model=TokenResponse, summary="Đăng nhập OAuth2")
def oauth_login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
):
    """Endpoint form chuẩn OAuth2 dành cho Swagger và các client cũ."""
    enforce_login_rate_limit(request, db)
    auth_service = AuthService()
    user = auth_service.authenticate_user(
        db=db,
        username=form.username,
        password=form.password,
    )
    return {
        "access_token": auth_service.create_access_token(
            user_id=user.id,
            username=user.username,
            role=str(user.role.name) if user.role else "",
            password_hash=user.password_hash,
        ),
        "token_type": "bearer",
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
        "full_name": current_user.full_name,
        "role": str(current_user.role.name) if current_user.role else "",
        "is_active": current_user.is_active,
    }


@router.put("/me", response_model=CurrentUserResponse, summary="Cập nhật hồ sơ cá nhân")
def update_me(
    body: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    existing = db.query(User).filter(
        User.username == body.username,
        User.id != current_user.id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã tồn tại",
        )

    current_user.username = body.username
    current_user.full_name = body.full_name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tên đăng nhập đã tồn tại",
        )
    db.refresh(current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
        "role": str(current_user.role.name) if current_user.role else "",
        "is_active": current_user.is_active,
    }


@router.put("/me/password", status_code=status.HTTP_200_OK, summary="Đổi mật khẩu")
def change_password(
    body: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    auth_service = AuthService()
    expected_hash = current_user.password_hash
    if not auth_service.verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu hiện tại không đúng",
        )
    if auth_service.verify_password(body.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu mới phải khác mật khẩu hiện tại",
        )

    new_hash = auth_service.get_password_hash(body.new_password)
    # The password validated above may have changed in a concurrent admin reset.
    # Compare-and-swap prevents a stale request from overwriting that newer reset.
    result = db.execute(update(User).where(
        User.id == current_user.id,
        User.password_hash == expected_hash,
        User.is_active.is_(True),
    ).values(password_hash=new_hash).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Thông tin đăng nhập đã thay đổi. Vui lòng đăng nhập lại.")
    db.commit()
    return {"message": "Đổi mật khẩu thành công. Vui lòng đăng nhập lại trên các thiết bị."}
