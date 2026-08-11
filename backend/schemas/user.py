from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.role import RoleResponse


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=100)
    is_active: bool = True
    role_id: int = Field(gt=0)

    @field_validator("username", "full_name", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_bcrypt_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte")
        return value


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: Optional[bool] = None
    role_id: Optional[int] = Field(default=None, gt=0)
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)

    @field_validator("username", "full_name", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def validate_optional_bcrypt_length(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu không được vượt quá 72 byte")
        return value


class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None
    role: RoleResponse

    model_config = ConfigDict(from_attributes=True)
