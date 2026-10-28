from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
import re
from typing import Optional

from email_validator import EmailNotValidError, validate_email

PHONE_INVALID = "Số điện thoại không hợp lệ: chỉ gồm 8–15 chữ số, có thể có dấu +, khoảng trắng, dấu chấm hoặc gạch ngang."
EMAIL_INVALID = "Email không hợp lệ."


def validate_phone_number(value: str) -> str:
    """Review 28/10/2026 R1-PHONE-EMAIL: a new or changed phone is a real phone number.

    Stored values that predate this rule (seeded "DEMO-CUSTOMER-1") stay
    editable as long as they are sent back unchanged (see routers/customer.py).
    """
    if not re.fullmatch(r"\+?[0-9][0-9 .()-]*", value) or not 8 <= sum(char.isdigit() for char in value) <= 15:
        raise ValueError(PHONE_INVALID)
    return value


def validate_email_address(value: str) -> str:
    """Syntax check only, no DNS; a new or changed email must be a usable address."""
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError(EMAIL_INVALID) from None

# Schema gốc (khớp với models/customer.py)
class CustomerBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=1, max_length=20)
    # customers.email is VARCHAR(100): reject longer addresses with 422 instead of a DB error (#68).
    email: Optional[EmailStr] = Field(default=None, max_length=100)

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
    @field_validator("phone_number")
    @classmethod
    def check_phone(cls, value):
        return validate_phone_number(value)

# Schema cho PUT
class CustomerUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(default=None, min_length=1, max_length=20)
    # Validated by the router only when it differs from the stored value, so a
    # row seeded before these rules (example.invalid) stays editable (R1-PHONE-EMAIL).
    email: Optional[str] = Field(default=None, max_length=100)

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
    # Rows may predate the current EmailStr write contract. Reading stored
    # data must not make an entire list endpoint fail after a successful write.
    email: Optional[str] = Field(default=None, max_length=100)

    model_config = ConfigDict(from_attributes=True)
