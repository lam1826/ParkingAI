from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional

# Schema gốc (khớp với models/customer.py)
class CustomerBase(BaseModel):
    full_name: str
    phone_number: str
    email: Optional[EmailStr] = None

# Schema cho POST
class CustomerCreate(CustomerBase):
    pass

# Schema cho PUT
class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None

# Schema trả về
class CustomerResponse(CustomerBase):
    id: int

    model_config = ConfigDict(from_attributes=True)