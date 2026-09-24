from pydantic import BaseModel, ConfigDict, Field, StrictBool


class AutomationPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool
    minimum_confidence: float = Field(default=0.97, ge=0.9, le=1, allow_inf_nan=False)
    max_age_seconds: int = Field(default=15, ge=3, le=30, strict=True)
