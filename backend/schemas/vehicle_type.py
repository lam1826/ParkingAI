from pydantic import BaseModel, ConfigDict
from typing import Optional

# Schema gốc
class VehicleTypeBase(BaseModel):
    name: str
    description: Optional[str] = None

# Schema cho POST
class VehicleTypeCreate(VehicleTypeBase):
    pass

# Schema cho PUT
class VehicleTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

# Schema trả về cho GET, POST, PUT
class VehicleTypeResponse(VehicleTypeBase):
    id: int

    model_config = ConfigDict(from_attributes=True)