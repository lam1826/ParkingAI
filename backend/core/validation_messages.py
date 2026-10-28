"""Short Vietnamese texts for request validation errors (review 28/10/2026 B-05/N-2, R2-05).

A 422 keeps FastAPI's list shape (``type`` and ``loc`` for clients and tests)
but never echoes the submitted value (``input``), the validator context
(regex patterns, limits as raw objects) or pydantic's English ``msg``: the
screens show ``msg`` as is, so it is a short Vietnamese sentence here.
"""

FIELD_LABELS = {
    "username": "Tên đăng nhập", "password": "Mật khẩu", "current_password": "Mật khẩu hiện tại",
    "new_password": "Mật khẩu mới", "full_name": "Họ tên", "phone_number": "Số điện thoại", "email": "Email",
    "license_plate": "Biển số", "vehicle_type_id": "Loại xe", "vehicle_id": "Phương tiện", "customer_id": "Khách hàng",
    "capacity": "Sức chứa", "code_prefix": "Tiền tố mã", "name": "Tên", "price": "Giá", "amount": "Số tiền",
    "site_id": "Bãi", "zone_id": "Khu vực", "slot_name": "Tên vị trí", "parking_slot_id": "Vị trí",
    "note": "Ghi chú", "reason": "Lý do", "message": "Nội dung", "subject": "Tiêu đề", "description": "Mô tả",
    "start_at": "Giờ bắt đầu", "end_at": "Giờ kết thúc", "start_date": "Ngày bắt đầu", "end_date": "Ngày kết thúc",
    "anchor_date": "Ngày báo cáo", "date_from": "Từ ngày", "date_to": "Đến ngày", "period": "Kỳ báo cáo",
    "duration_minutes": "Thời lượng (phút)", "duration_days": "Số ngày", "limit": "Số dòng", "offset": "Vị trí bắt đầu",
    "skip": "Vị trí bắt đầu", "page": "Trang", "page_size": "Số dòng mỗi trang", "size": "Số dòng mỗi trang",
    "registration_code": "Mã đăng ký", "role": "Vai trò", "role_id": "Vai trò", "is_active": "Trạng thái",
    "pass_code": "Mã thẻ", "question": "Câu hỏi", "body": "Dữ liệu gửi lên",
}
COMPARISONS = {"greater_than": ("gt", "phải lớn hơn"), "greater_than_equal": ("ge", "phải lớn hơn hoặc bằng"),
               "less_than": ("lt", "phải nhỏ hơn"), "less_than_equal": ("le", "phải nhỏ hơn hoặc bằng")}


def _detail(kind: str, ctx: dict, msg: str) -> tuple[str, bool]:
    """(text, labelled): a validator's own Vietnamese sentence is shown without a field prefix."""
    if kind in {"value_error", "assertion_error"}:
        text = msg.split(", ", 1)[1] if msg.startswith(("Value error, ", "Assertion failed, ")) else msg
        if "email" in text.lower() and text.isascii():
            return "email không hợp lệ.", True
        return (text, False) if not text.isascii() else ("giá trị không hợp lệ.", True)
    if kind == "missing":
        return "bắt buộc nhập.", True
    if kind == "string_too_short":
        return f"cần ít nhất {ctx.get('min_length')} ký tự.", True
    if kind == "string_too_long":
        return f"tối đa {ctx.get('max_length')} ký tự.", True
    if kind == "too_short":
        return f"cần ít nhất {ctx.get('min_length')} mục.", True
    if kind == "too_long":
        return f"tối đa {ctx.get('max_length')} mục.", True
    if kind == "string_pattern_mismatch":
        return "sai định dạng.", True
    if kind in COMPARISONS:
        key, text = COMPARISONS[kind]
        return f"{text} {ctx.get(key)}.", True
    if kind.startswith("int_"):
        return "phải là số nguyên.", True
    if kind.startswith(("float_", "decimal_")) or kind == "finite_number":
        return "phải là số hợp lệ.", True
    if kind.startswith("bool_"):
        return "phải là đúng hoặc sai.", True
    if kind.startswith(("datetime_", "timezone_")):
        return "thời gian không hợp lệ.", True
    if kind.startswith("date_"):
        return "ngày không hợp lệ.", True
    if kind.startswith("time_"):
        return "giờ không hợp lệ.", True
    if kind in {"literal_error", "enum"}:
        return "giá trị không nằm trong danh sách cho phép.", True
    if kind == "json_invalid":
        return "dữ liệu JSON không hợp lệ.", True
    if kind == "extra_forbidden":
        return "trường này không được phép.", True
    if kind.startswith("uuid"):
        return "mã không hợp lệ.", True
    if kind in {"string_type", "string_unicode"}:
        return "phải là chuỗi ký tự.", True
    if kind in {"list_type", "tuple_type", "set_type"}:
        return "phải là danh sách.", True
    if kind in {"dict_type", "model_type", "model_attributes_type", "dataclass_type"}:
        return "sai cấu trúc dữ liệu.", True
    return "giá trị không hợp lệ.", True


def vietnamese_error(error: dict) -> dict:
    loc = list(error.get("loc", ()))
    field = next((str(part) for part in reversed(loc) if isinstance(part, str) and part not in {"query", "path", "header"}), "")
    text, labelled = _detail(str(error.get("type", "")), error.get("ctx") or {}, str(error.get("msg", "")))
    label = FIELD_LABELS.get(field) if labelled else None
    # A validator's own sentence is kept verbatim; a generated one starts with a capital.
    message = f"{label}: {text}" if label else text if not labelled else text[:1].upper() + text[1:]
    return {"type": error.get("type"), "loc": [part if isinstance(part, (str, int)) else str(part) for part in loc],
            "msg": message}
