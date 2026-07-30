from pydantic import BaseModel, ConfigDict
from typing import Optional

# Schema gốc (khớp với models/vehicle.py)
class VehicleBase(BaseModel):
    license_plate: str
    vehicle_type_id: int
    customer_id: Optional[int] = None  # Khách vãng lai thì không có customer_id

# Schema cho POST
class VehicleCreate(VehicleBase):
    pass

# Schema cho PUT
class VehicleUpdate(BaseModel):
    license_plate: Optional[str] = None
    vehicle_type_id: Optional[int] = None
    customer_id: Optional[int] = None

# Schema trả về
class VehicleResponse(VehicleBase):
    id: int

    model_config = ConfigDict(from_attributes=True)