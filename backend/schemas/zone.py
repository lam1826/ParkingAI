from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class ZoneBase(BaseModel):
    name: str
    capacity: int = Field(..., ge=0, description="Sức chứa tối đa của khu vực")
    is_active: bool = True

class ZoneCreate(ZoneBase):
    pass

class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None

class ZoneResponse(ZoneBase):
    id: int

    model_config = ConfigDict(from_attributes=True)