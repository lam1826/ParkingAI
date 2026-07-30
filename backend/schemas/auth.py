from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class LoginRequest(BaseModel):
    """Schema cho request đăng nhập (nếu dùng JSON body thay vì Form Data)."""
    username: str = Field(..., description="Tên đăng nhập")
    password: str = Field(..., description="Mật khẩu")

class TokenResponse(BaseModel):
    """Schema trả về JWT Access Token sau khi đăng nhập thành công."""
    access_token: str = Field(..., description="Mã JWT Token")
    token_type: str = Field(default="bearer", description="Loại token")

    model_config = ConfigDict(from_attributes=True)

class CurrentUserResponse(BaseModel):
    """Schema trả về thông tin cá nhân của người dùng hiện tại (Endpoint /auth/me)."""
    id: int
    username: str
    role: str
    is_active: Optional[bool] = True

    model_config = ConfigDict(from_attributes=True)