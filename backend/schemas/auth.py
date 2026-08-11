from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., description="Tên đăng nhập")
    password: str = Field(..., description="Mật khẩu")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=100)
    role: Literal["customer", "manager", "admin"] = "customer"
    registration_code: Optional[str] = Field(default=None, max_length=255)

    @field_validator("username", "full_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Trường này không được để trống")
        return value

    @field_validator("password")
    @classmethod
    def validate_bcrypt_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte")
        return value


class RegisterResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Mã JWT")
    token_type: str = Field(default="bearer", description="Loại token")

    model_config = ConfigDict(from_attributes=True)


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: Optional[bool] = True

    model_config = ConfigDict(from_attributes=True)


class UpdateProfileRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=100)

    @field_validator("username", "full_name", mode="before")
    @classmethod
    def strip_profile_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("current_password", "new_password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte")
        return value
