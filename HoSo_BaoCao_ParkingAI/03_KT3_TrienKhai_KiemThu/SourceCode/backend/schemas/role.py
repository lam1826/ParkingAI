from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.roles import CANONICAL_ROLE_NAMES

# Base schema dùng chung
class RoleBase(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def normalize_canonical_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in CANONICAL_ROLE_NAMES:
            allowed = ", ".join(sorted(CANONICAL_ROLE_NAMES))
            raise ValueError(f"Vai trò phải thuộc một trong các giá trị: {allowed}")
        return normalized

# Schema cho POST (Tạo mới)
class RoleCreate(RoleBase):
    pass

# Schema cho PUT (Cập nhật - các field có thể None nếu không muốn đổi)
class RoleUpdate(BaseModel):
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
    def normalize_canonical_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in CANONICAL_ROLE_NAMES:
            allowed = ", ".join(sorted(CANONICAL_ROLE_NAMES))
            raise ValueError(f"Vai trò phải thuộc một trong các giá trị: {allowed}")
        return normalized

# Schema trả về chỉ serialize dữ liệu. Không kế thừa validator canonical của
# write contract để một role legacy không làm hỏng toàn bộ endpoint danh sách.
class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    # Pydantic v2 thay thế class Config(orm_mode=True) bằng ConfigDict
    model_config = ConfigDict(from_attributes=True)
