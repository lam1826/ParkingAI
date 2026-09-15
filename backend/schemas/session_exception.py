from pydantic import BaseModel, ConfigDict, Field, field_validator


class SessionExceptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)
    request_id: str = Field(min_length=1, max_length=64)

    @field_validator("reason", "request_id", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PlateCorrectionRequest(SessionExceptionRequest):
    license_plate: str = Field(min_length=4, max_length=15)

    @field_validator("license_plate", mode="before")
    @classmethod
    def normalize_plate(cls, value):
        return value.strip().upper() if isinstance(value, str) else value
