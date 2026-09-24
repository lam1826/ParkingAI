from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class FeeLookup(CustomerInput):
    site_id: int = Field(strict=True, gt=0)
    license_plate: str = Field(min_length=1, max_length=20)
    vehicle_type_id: int = Field(strict=True, gt=0)
    ticket_proof: str | None = Field(default=None, max_length=160)


class AdvanceBookingCreate(CustomerInput):
    site_id: int = Field(strict=True, gt=0)
    license_plate: str = Field(default='', max_length=20)
    vehicle_type_id: int = Field(strict=True, gt=0)
    start_at: AwareDatetime
    end_at: AwareDatetime
    request_id: str = Field(min_length=16, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')

    @model_validator(mode='after')
    def interval(self):
        if self.end_at <= self.start_at or (self.end_at-self.start_at).total_seconds() > 30*86400:
            raise ValueError('Khoảng đặt chỗ phải dương và không quá 30 ngày.')
        return self
