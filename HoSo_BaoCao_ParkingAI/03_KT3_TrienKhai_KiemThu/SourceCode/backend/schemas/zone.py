import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Any, Optional

class ZoneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    capacity: int = Field(..., ge=0, description="Sức chứa tối đa của khu vực")
    is_active: bool = True

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return unicodedata.normalize("NFC", value.strip())

class ZoneCreate(ZoneBase):
    pass

class ZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    capacity: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field in ("name", "capacity", "is_active"):
                if field in data and data[field] is None:
                    raise ValueError(f"{field} không được nhận giá trị null")
        return data

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return unicodedata.normalize("NFC", value.strip())

class ZoneResponse(ZoneBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
