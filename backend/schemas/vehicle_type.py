import unicodedata
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Schema gốc
class VehicleTypeBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return unicodedata.normalize("NFC", value.strip())

# Schema cho POST
class VehicleTypeCreate(VehicleTypeBase):
    pass

# Schema cho PUT
class VehicleTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_name(cls, data: Any) -> Any:
        if isinstance(data, dict) and "name" in data and data["name"] is None:
            raise ValueError("name không được nhận giá trị null")
        return data

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return unicodedata.normalize("NFC", value.strip())

# Schema trả về cho GET, POST, PUT
class VehicleTypeResponse(VehicleTypeBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
