from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional
from datetime import date


def _normalize_pass_code(value):
    """Mã thẻ NFC/RFID: trim và chuẩn hóa chữ hoa trước khi validate/lưu."""
    return value.strip().upper() if isinstance(value, str) else value


# Schema gốc
class MonthlyPassBase(BaseModel):
    customer_id: int
    vehicle_id: int
    pass_code: str = Field(min_length=1, max_length=50)
    price: int = Field(ge=0, description="Số tiền thực thu (VND), số nguyên không âm")
    start_date: date
    end_date: date
    is_active: bool = True

    # Không âm thầm bỏ field ngoài schema — payload lạ phải bị từ chối (422)
    model_config = ConfigDict(extra="forbid")

    @field_validator("pass_code", mode="before")
    @classmethod
    def normalize_pass_code(cls, value):
        return _normalize_pass_code(value)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi")
        return self

# Schema cho POST (Thêm mới vé tháng)
class MonthlyPassCreate(MonthlyPassBase):
    pass

# Schema cho PUT (Gia hạn, hủy kích hoạt hoặc cập nhật một phần)
class MonthlyPassUpdate(BaseModel):
    customer_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    pass_code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    price: Optional[int] = Field(default=None, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null(cls, data):
        """Partial update: field bị BỎ QUA thì hợp lệ, nhưng field có mặt với
        giá trị null phải bị từ chối 422 — không field nào của vé tháng được
        phép xóa thành NULL (kể cả pass_code: bản ghi cũ NULL chỉ là di sản,
        không phải trạng thái được phép quay lại). Chặn tại Pydantic để router
        không bao giờ nhận None rồi crash 500 hoặc ghi NULL vào cột bắt buộc."""
        if isinstance(data, dict):
            null_fields = [
                key for key in cls.model_fields if key in data and data[key] is None
            ]
            if null_fields:
                raise ValueError(
                    "Các field sau không được phép là null: "
                    + ", ".join(null_fields)
                    + ". Hãy bỏ hẳn field khỏi payload nếu không muốn cập nhật."
                )
        return data

    @field_validator("pass_code", mode="before")
    @classmethod
    def normalize_pass_code(cls, value):
        return _normalize_pass_code(value)

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi")
        return self

# Thông tin rút gọn của xe/khách hàng nhúng trong response vé tháng.
# Contract thống nhất với frontend: bảng vé tháng đọc vehicle.license_plate
# và customer.full_name — không để frontend phải đoán nhiều shape.
class MonthlyPassVehicleInfo(BaseModel):
    id: int
    license_plate: str

    model_config = ConfigDict(from_attributes=True)


class MonthlyPassCustomerInfo(BaseModel):
    id: int
    full_name: str
    phone_number: str

    model_config = ConfigDict(from_attributes=True)


# Schema trả về — cố ý KHÔNG kế thừa MonthlyPassBase: response chỉ serialize,
# không chạy lại validator nghiệp vụ (một bản ghi cũ lỡ sai khoảng ngày sẽ không
# làm 500 toàn bộ GET danh sách; việc chặn dữ liệu sai là trách nhiệm của khâu ghi).
class MonthlyPassResponse(BaseModel):
    id: int
    customer_id: int
    vehicle_id: int
    pass_code: Optional[str] = None  # bản ghi cũ (trước khi có cột) có thể NULL
    price: int = 0
    start_date: date
    end_date: date
    is_active: bool
    vehicle: Optional[MonthlyPassVehicleInfo] = None
    customer: Optional[MonthlyPassCustomerInfo] = None

    model_config = ConfigDict(from_attributes=True)
