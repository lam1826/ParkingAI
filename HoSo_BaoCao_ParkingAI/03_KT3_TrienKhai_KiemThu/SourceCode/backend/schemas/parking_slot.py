from pydantic import BaseModel, ConfigDict
from typing import Optional

# Schema gốc (khớp với models/parking_slot.py)
class ParkingSlotBase(BaseModel):
    slot_name: str
    zone_id: int
    vehicle_type_id: int
    is_occupied: bool = False
    is_active: bool = True

# Schema cho POST
class ParkingSlotCreate(ParkingSlotBase):
    pass

# Schema cho PUT
class ParkingSlotUpdate(BaseModel):
    slot_name: Optional[str] = None
    zone_id: Optional[int] = None
    vehicle_type_id: Optional[int] = None
    is_occupied: Optional[bool] = None
    is_active: Optional[bool] = None

# Schema trả về cho GET, POST, PUT
class ParkingSlotResponse(ParkingSlotBase):
    id: int

    model_config = ConfigDict(from_attributes=True)