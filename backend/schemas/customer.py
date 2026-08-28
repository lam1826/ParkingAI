from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from typing import Optional

# Schema gốc (khớp với models/customer.py)
class CustomerBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=1, max_length=20)
    email: Optional[EmailStr] = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

# Schema cho POST
class CustomerCreate(CustomerBase):
    pass

# Schema cho PUT
class CustomerUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(default=None, min_length=1, max_length=20)
    email: Optional[EmailStr] = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_for_required_fields(cls, data):
        if isinstance(data, dict):
            for field_name in ("full_name", "phone_number"):
                if field_name in data and data[field_name] is None:
                    raise ValueError(f"{field_name} không được là null")
        return data

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None
        return value

# Schema trả về
class CustomerResponse(CustomerBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
