import datetime
import bcrypt
from typing import Dict, Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session  # Sửa từ AsyncSession thành Session đồng bộ

from core.config import settings
from database import get_db
from models.user import User

# ==========================================
# 1. SETUP BẢO MẬT & MÃ HÓA
# ==========================================

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ROLE_HIERARCHY: Dict[str, int] = {
    "staff": 1,
    "manager": 2,
    "admin": 3
}

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
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Băm (hash) mật khẩu trước khi lưu vào DB."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def create_access_token(self, user_id: int, username: str, role: str) -> str:
        """Tạo JWT Access Token."""
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "role": role,
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
        # Sử dụng cú pháp query đồng bộ thay vì execute async
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
        
        if user_id_str is None:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
        
    try:
        user_id = int(user_id_str)
    except ValueError:
        raise credentials_exception

    # Truy vấn đồng bộ
    user = db.query(User).filter(User.id == user_id).first()
    
    if user is None:
        raise credentials_exception
        
    return user


# ==========================================
# 4. PHÂN QUYỀN - RBAC (Role-Based Access)
# ==========================================

def check_permission(current_user: User, required_role: str) -> bool:
    user_role_str = str(current_user.role.name).lower() if current_user.role else ""
    required_role_str = required_role.lower()
    
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