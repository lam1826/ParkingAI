"""Explainable hourly seasonality with rolling-origin evaluation; no LLM numbers."""
import math
from datetime import timedelta
from statistics import mean

from core.clock import BUSINESS_TZ

MIN_HISTORY_DAYS = 42
MAX_HISTORY_DAYS = 84
SEASONAL_WEEKS = 12
# Sparse-history thresholds: share of days / hourly buckets with an arrival record (>0) in the window.
SPARSE_DAY_RATIO = 0.6
SPARSE_HOUR_RATIO = 0.15
COMPLETENESS_NOTE = ("Giờ không có bản ghi được xem là 0 lượt xe vào. Hệ thống không có nhật ký hoạt động của nguồn ghi nhận "
                     "(camera/nhân viên), nên chưa xác định được mức đầy đủ của quan sát; không kết luận mất dữ liệu hay "
                     "giờ thực sự vắng xe từ các con số này.")


def _hour(value):
    if value.tzinfo is not None:
        value = value.astimezone(BUSINESS_TZ).replace(tzinfo=None)
    return value.replace(minute=0, second=0, microsecond=0)


def _quantile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def _seasonal(values, target, start):
    samples = [values.get(target - timedelta(weeks=week), 0) for week in range(1, SEASONAL_WEEKS + 1)
               if target - timedelta(weeks=week) >= start]
    return mean(samples) if samples else 0.0, samples


def _coverage(arrivals, departures, start, cutoff, days):
    hours_in_window = int((cutoff - start).total_seconds() // 3600)
    hours_with_arrivals = sum(1 for value in arrivals.values() if value > 0)
    days_with_arrivals = len({key.date() for key, value in arrivals.items() if value > 0})
    return {"history_days": days, "required_days": MIN_HISTORY_DAYS, "window_start": start.replace(tzinfo=BUSINESS_TZ).isoformat(),
            "window_end": cutoff.replace(tzinfo=BUSINESS_TZ).isoformat(), "days_with_arrivals": days_with_arrivals,
            "hours_in_window": hours_in_window, "hours_with_arrivals": hours_with_arrivals,
            "hours_with_departures": sum(1 for key, value in departures.items() if value > 0 and start <= key < cutoff),
            "hours_zero_filled": hours_in_window - hours_with_arrivals, "observation_completeness": "unknown",
            "completeness_note": COMPLETENESS_NOTE,
            "sparse_history": days_with_arrivals < SPARSE_DAY_RATIO * days or hours_with_arrivals < SPARSE_HOUR_RATIO * hours_in_window}


def build_forecast(arrivals, departures, now, horizon_hours=24):
    if not isinstance(horizon_hours, int) or not 1 <= horizon_hours <= 48:
        raise ValueError("Horizon must be 1 to 48 hours")
    if now.tzinfo is not None:
        now = now.astimezone(BUSINESS_TZ).replace(tzinfo=None)
    cutoff = _hour(now)
    lower_bound = cutoff - timedelta(days=MAX_HISTORY_DAYS)
    def clean(values):
        result = {}
        for key, value in values.items():
            timestamp = _hour(key)
            if lower_bound <= timestamp < cutoff:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError("Hourly counts must be finite and nonnegative")
                result[timestamp] = result.get(timestamp, 0) + value
        return result
    arrivals, departures = clean(arrivals), clean(departures)
    start = min(arrivals, default=cutoff)
    days = max(0, (cutoff - start).days)
    coverage = _coverage(arrivals, departures, start, cutoff, days)
    base = {"status": "insufficient_data", "model": "same_weekday_hour_mean", "as_of": now.replace(tzinfo=BUSINESS_TZ).isoformat(),
            "coverage": coverage,
            "backtest": {"method": "rolling_origin", "mae": None, "baseline_mae": None, "samples": 0}, "predictions": [],
            "warnings": ["Giờ không có bản ghi được xem là 0 lượt; cần đối chiếu nhật ký mất dữ liệu trước khi sử dụng dự báo.",
                         "Khoảng dự báo phản ánh biến động lịch sử, chưa được hiệu chuẩn bằng dữ liệu camera thực tế."]}
    if coverage["sparse_history"]:
        base["warnings"].append(f"Lịch sử thưa: chỉ {coverage['days_with_arrivals']}/{days} ngày và {coverage['hours_with_arrivals']}/"
                                f"{coverage['hours_in_window']} giờ có bản ghi xe vào; phần lớn ước lượng dựa trên giờ được điền 0.")
    if days < MIN_HISTORY_DAYS:
        base["warnings"].append(f"Cần ít nhất {MIN_HISTORY_DAYS} ngày lịch sử trước giờ hiện tại; chưa sinh dự báo.")
        return base
    # Every target sees only earlier weekly buckets. Test labels never enter
    # its predictor, even though the complete history is in memory.
    errors, naive_errors = [], []
    target = max(start + timedelta(days=28), cutoff - timedelta(days=14))
    while target < cutoff:
        predicted, _ = _seasonal(arrivals, target, start)
        actual = arrivals.get(target, 0)
        errors.append(abs(predicted - actual))
        naive_errors.append(abs(arrivals.get(target - timedelta(weeks=1), 0) - actual))
        target += timedelta(hours=1)
    mae = mean(errors)
    base["status"] = "ready"
    base["backtest"] = {"method": "rolling_origin", "mae": round(mae, 3), "baseline_mae": round(mean(naive_errors), 3), "samples": len(errors)}
    first = cutoff + timedelta(hours=int(now.replace(tzinfo=None) > cutoff))
    for offset in range(horizon_hours):
        at = first + timedelta(hours=offset)
        # Forecast only from observations earlier than cutoff; for horizons
        # under a week each seasonal reference is in the training period.
        predicted, samples = _seasonal(arrivals, at, start)
        outgoing, _ = _seasonal(departures, at, start)
        observed = sum(1 for sample in samples if sample > 0)
        base["predictions"].append({"at": at.replace(tzinfo=BUSINESS_TZ).isoformat(), "arrivals": round(predicted, 2),
            "departures": round(outgoing, 2), "lower": round(max(0.0, min(predicted, _quantile(samples, .1) - mae)), 2),
            "upper": round(max(predicted, _quantile(samples, .9) + mae), 2),
            "samples_observed": observed, "samples_zero_filled": len(samples) - observed})
    if base["backtest"]["mae"] > base["backtest"]["baseline_mae"]:
        base["warnings"].append("Mô hình chưa tốt hơn cách lấy cùng giờ tuần trước. Chỉ dùng để tham khảo.")
    return base


def build_staff_plan(forecast, *, service_seconds, utilization, min_staff, max_staff):
    if not 5 <= service_seconds <= 600 or not .3 <= utilization <= .95 or not 0 <= min_staff <= max_staff <= 50 or max_staff < 1:
        raise ValueError("Invalid staffing assumptions")
    capacity = 3600 / service_seconds * utilization
    plan = []
    for prediction in forecast["predictions"]:
        workload = prediction["arrivals"] + prediction.get("departures", 0)
        required = max(min_staff, math.ceil(workload / capacity))
        assigned = min(required, max_staff)
        plan.append({"at": prediction["at"], "arrivals": prediction["arrivals"], "departures": prediction.get("departures", 0),
                     "staff_required": required, "staff_assigned": assigned, "capacity_shortfall": round(max(0, workload - assigned * capacity), 2)})
    return {"status": forecast["status"], "assumptions": {"service_seconds_per_vehicle": service_seconds,
        "utilization_target": utilization, "min_staff": min_staff, "max_staff": max_staff, "capacity_per_staff_hour": round(capacity, 2)},
        "plan": plan, "warnings": ["Tính cả xe vào và xe ra; giả định mỗi lượt cần một lần phục vụ.",
                                    "Đây là nhu cầu theo giờ, không tự phân công nhân viên hoặc thay thế lịch nghỉ và quy định ca."]}
