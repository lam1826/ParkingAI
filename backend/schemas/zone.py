import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from typing import Any, Optional

# zones.capacity is INTEGER (32-bit) on PostgreSQL. Bound write requests so an oversized
# value is a 422, not a database error / HTTP 500 (#68). Responses keep the plain base field.
MAX_ZONE_CAPACITY = 2_147_483_647

class ZoneBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    capacity: StrictInt = Field(..., ge=0, description="Sức chứa tối đa của khu vực")
    is_active: bool = True

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return unicodedata.normalize("NFC", value.strip())

class ZoneCreate(ZoneBase):
    capacity: StrictInt = Field(..., ge=0, le=MAX_ZONE_CAPACITY, description="Sức chứa tối đa của khu vực")

class ZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    capacity: Optional[StrictInt] = Field(default=None, ge=0, le=MAX_ZONE_CAPACITY)
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
    # Read-only site of the zone. The global catalog page needs it to show only the
    # configured lot in single-site mode (#77); the legacy write payload still cannot set it.
    site_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ZoneCreationScope(BaseModel):
    """Whether the legacy (site-less) zone form can create a zone at all (#71)."""
    legacy_create_allowed: bool
    detail: Optional[str] = None
