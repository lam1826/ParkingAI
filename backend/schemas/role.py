from pydantic import BaseModel, ConfigDict
from typing import Optional

# Base schema dùng chung
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

# Schema cho POST (Tạo mới)
class RoleCreate(RoleBase):
    pass

# Schema cho PUT (Cập nhật - các field có thể None nếu không muốn đổi)
class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

# Schema trả về (GET, POST response)
class RoleResponse(RoleBase):
    id: int

    # Pydantic v2 thay thế class Config(orm_mode=True) bằng ConfigDict
    model_config = ConfigDict(from_attributes=True)