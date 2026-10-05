import datetime
import bcrypt
import hashlib
import hmac
import jwt
import secrets
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session  # Sửa từ AsyncSession thành Session đồng bộ

from core.config import settings
from core.roles import ROLE_HIERARCHY
from database import get_db
from models.user import User

# ==========================================
# 1. SETUP BẢO MẬT & MÃ HÓA
# ==========================================

# tokenUrl trỏ tới endpoint OAuth2 form (/auth/login), không phải endpoint JSON
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ==========================================
# 2. LỚP AUTH SERVICE (Nghiệp vụ cốt lõi)
# ==========================================

class AuthService:
    """
    Xử lý toàn bộ logic liên quan đến xác thực (Authentication).
    """
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Kiểm tra mật khẩu chưa mã hóa với hash lưu trong DB."""
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Băm (hash) mật khẩu trước khi lưu vào DB."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def credential_version(user_id: int, password_hash: str) -> str:
        """Bind sessions to credentials without exposing the stored bcrypt hash.

        A new salted password hash (including an admin reset to the same password)
        invalidates previous tokens without a timestamp race or a schema change.
        Domain separation keeps this MAC distinct from JWT signing and other keys.
        """
        message = f"parkingai:credential-version:v1\0{user_id}\0{password_hash}"
        return hmac.new(settings.SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_access_token(self, user_id: int, username: str, role: str, *, password_hash: str) -> str:
        """Issue a bearer bound to the password snapshot authenticated at login."""
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "role": role,
            "credential_version": self.credential_version(user_id, password_hash),
            "exp": expire
        }
        
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.SECRET_KEY, 
            algorithm=settings.ALGORITHM
        )
        return encoded_jwt

    def authenticate_user(
        self, 
        db: Session,  # Sử dụng Session đồng bộ
        username: str, 
        password: str
    ) -> User:
        """Truy vấn DB và xác thực thông tin người dùng (Đồng bộ)."""
        # Stored usernames never contain surrounding whitespace (JSON and OAuth form login).
        username = username.strip() if isinstance(username, str) else username
        user = db.query(User).filter(User.username == username).first()
        
        if not user or not self.verify_password(password, str(user.password_hash)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sai tên đăng nhập hoặc mật khẩu",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if getattr(user, "is_active", None) is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tài khoản đã bị khóa"
            )
            
        return user

    @staticmethod
    def validate_registration_role(role: str, registration_code: str | None) -> None:
        """Customer registration is public; privileged roles require a server-side code."""
        required_code = {
            "manager": settings.MANAGER_REGISTRATION_CODE,
            "admin": settings.ADMIN_REGISTRATION_CODE,
        }.get(role)

        if required_code is None:
            return
        if not required_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Đăng ký vai trò {role} chưa được quản trị viên bật",
            )
        if not registration_code or not secrets.compare_digest(registration_code, required_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mã đăng ký không hợp lệ",
            )


# ==========================================
# 3. FASTAPI DEPENDENCIES (Cấp độ Module)
# ==========================================

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)]  # Sử dụng Session đồng bộ
) -> User:
    """
    Dependency lấy và xác thực người dùng hiện tại từ JWT Token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Không thể xác thực thông tin (Token sai hoặc đã hết hạn)",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        user_id_str: str | None = payload.get("sub")
        
        if not isinstance(user_id_str, str) or not user_id_str.isascii() or not user_id_str.isdecimal():
            raise credentials_exception
            
    except InvalidTokenError:
        raise credentials_exception
        
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    # Avoid sending malformed/oversized subjects into a database integer column.
    if not 0 < user_id <= 2**63 - 1:
        raise credentials_exception

    # Truy vấn đồng bộ
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None or not user.is_active:
        raise credentials_exception

    credential_version = payload.get("credential_version")
    if (not isinstance(credential_version, str)
            or not credential_version.isascii()
            or not hmac.compare_digest(credential_version, AuthService.credential_version(user.id, user.password_hash))):
        # Legacy unbound tokens fail closed as well; login issues a bound token.
        raise credentials_exception
        
    return user


# ==========================================
# 4. PHÂN QUYỀN - RBAC (Role-Based Access)
# ==========================================

def check_permission(current_user: User, required_role: str) -> bool:
    user_role_str = str(current_user.role.name).lower() if current_user.role else ""
    required_role_str = required_role.lower()

    if required_role_str not in ROLE_HIERARCHY:
        # Role yêu cầu bị gõ sai/không tồn tại -> chặn lại thay vì mở toang endpoint
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cấu hình phân quyền không hợp lệ: role '{required_role}' không tồn tại."
        )

    user_level = ROLE_HIERARCHY.get(user_role_str, 0)
    required_level = ROLE_HIERARCHY.get(required_role_str, 0)
    
    if user_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền để thực hiện hành động này."
        )
        
    return True

class RoleChecker:
    def __init__(self, required_role: str):
        self.required_role = required_role

    def __call__(
        self, 
        current_user: Annotated[User, Depends(get_current_user)]
    ) -> User:
        check_permission(current_user, self.required_role)
        return current_user
