"""Semantic validation of the numeric fields accepted in custom AI context.

Keep descriptive/custom fields and the legacy active_sessions record list;
known measurements must use actual JSON numbers, never coerced text/bools.
"""
import math
import re

COUNT_FIELDS = {
    "total", "count", "entries", "exits", "total_entries", "total_exits",
    "total_vehicles", "total_vehicles_today", "total_slots", "available_slots",
    "occupied_slots", "active_sessions", "capacity", "total_sessions",
    "total_trips", "total_slots_active", "occupied_slots_active",
}
MONEY_FIELDS = {"revenue", "total_revenue", "total_revenue_today", "parking_fee", "average_fee",
                "parking_revenue", "monthly_pass_revenue", "refunds", "cash_receipts",
                "cash_refunds", "transfer_receipts", "transfer_refunds", "opening_cash", "counted_cash"}
SIGNED_MONEY_FIELDS = {"revenue", "total_revenue", "total_revenue_today", "net_revenue"}
PERCENT_FIELDS = {"occupancy_rate", "occupancy_rate_percentage"}


def validate_statistics(value, *, path="statistics", hourly=False):
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_statistics(item, path=f"{path}[{index}]", hourly=hourly)
    elif isinstance(value, dict):
        for key, item in value.items():
            field_path = f"{path}.{key}"
            if key == "active_sessions" and isinstance(item, list):
                if not all(isinstance(record, dict) for record in item):
                    raise ValueError(f"{field_path} phải là số lượt hoặc danh sách bản ghi")
            elif key in COUNT_FIELDS | MONEY_FIELDS | SIGNED_MONEY_FIELDS | PERCENT_FIELDS | {"hour"}:
                if type(item) not in (int, float) or abs(item) > 9_007_199_254_740_991 or not math.isfinite(item):
                    raise ValueError(f"{field_path} phải là số hợp lệ trong phạm vi an toàn")
                if item < 0 and key not in SIGNED_MONEY_FIELDS:
                    raise ValueError(f"{field_path} phải là số không âm hợp lệ")
                if (key in COUNT_FIELDS or key == "hour") and item != int(item):
                    raise ValueError(f"{field_path} phải là số nguyên")
                if key in (MONEY_FIELDS | SIGNED_MONEY_FIELDS) - {"average_fee"} and item != int(item):
                    raise ValueError(f"{field_path} phải là số nguyên đồng VND")
                if key in PERCENT_FIELDS and item > 100:
                    raise ValueError(f"{field_path} phải nằm trong khoảng 0 đến 100")
                if key == "hour" and item > 23:
                    raise ValueError(f"{field_path} phải nằm trong khoảng 0 đến 23")
            if hourly and key == "time_label" and (
                not isinstance(item, str) or not re.fullmatch(r"(?:[01]?\d|2[0-3]):00", item)
            ):
                raise ValueError(f"{field_path} phải là giờ hợp lệ, ví dụ 08:00")
            validate_statistics(item, path=field_path, hourly=hourly or key in {"hourly_traffic", "traffic_by_hour"})
    return value
