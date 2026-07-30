from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

# Schema gốc dùng chung
class UserBase(BaseModel):
    username: str
    full_name: str
    is_active: bool = True
    role_id: int

# Schema cho POST (Yêu cầu có password khi tạo mới)
class UserCreate(UserBase):
    password: str = Field(..., min_length=1)

# Schema cho PUT (Các trường có thể None nếu không update)
class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    role_id: Optional[int] = None
    password: Optional[str] = None

# Schema trả về (Ẩn password, hiển thị ID)
class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)