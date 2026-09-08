import math
import random
from datetime import datetime, timedelta, timezone

from expansion.forecast import SEASONAL_WEEKS, build_forecast, build_staff_plan


def history(days=70):
    start = datetime(2026, 1, 1)
    counts = {start + timedelta(hours=i): (i % 24) % 5 for i in range(days * 24)}
    return start, counts


def test_forecast_insufficient_history_never_fabricates_predictions():
    start, counts = history(5)
    result = build_forecast(counts, {}, start + timedelta(days=5))
    assert result["status"] == "insufficient_data"
    assert result["predictions"] == [] and result["backtest"]["mae"] is None


def test_forecast_ignores_future_records_and_partial_hour():
    start, counts = history()
    cutoff = start + timedelta(days=70, minutes=20)
    result = build_forecast(counts, {}, cutoff)
    dirty = counts | {cutoff.replace(minute=0): 999999, cutoff + timedelta(days=1): 999999}
    assert build_forecast(dirty, {}, cutoff) == result
    assert result["status"] == "ready" and result["backtest"]["samples"] > 0
    assert all(row["lower"] <= row["arrivals"] <= row["upper"] for row in result["predictions"])


def test_forecast_backtest_uses_only_training_data_before_each_test_hour():
    start, counts = history()
    result = build_forecast(counts, {}, start + timedelta(days=70))
    assert result["backtest"]["mae"] == 0
    assert result["backtest"]["baseline_mae"] == 0
    assert result["backtest"]["method"] == "rolling_origin"


def test_empty_history_reports_zero_coverage_and_unknown_completeness():
    result = build_forecast({}, {}, datetime(2026, 3, 1, 9))
    coverage = result["coverage"]
    assert result["status"] == "insufficient_data" and result["predictions"] == []
    assert coverage["hours_in_window"] == 0 and coverage["hours_with_arrivals"] == 0 and coverage["hours_with_departures"] == 0
    assert coverage["hours_zero_filled"] == 0 and coverage["days_with_arrivals"] == 0
    assert coverage["observation_completeness"] == "unknown" and "nhật ký" in coverage["completeness_note"]
    assert coverage["sparse_history"] is False


def test_sparse_history_is_flagged_with_warning():
    start = datetime(2026, 1, 1)
    counts = {start + timedelta(days=day, hours=8): 3 for day in range(50)}
    counts[start] = 1
    result = build_forecast(counts, {}, start + timedelta(days=50))
    coverage = result["coverage"]
    assert result["status"] == "ready" and coverage["history_days"] == 50
    assert coverage["hours_in_window"] == 50 * 24 and coverage["hours_with_arrivals"] == 51
    assert coverage["hours_zero_filled"] == coverage["hours_in_window"] - coverage["hours_with_arrivals"]
    assert coverage["sparse_history"] is True
    assert any(warning.startswith("Lịch sử thưa:") for warning in result["warnings"])


def test_dense_history_is_not_flagged_sparse():
    start, counts = history()
    result = build_forecast(counts, {}, start + timedelta(days=70))
    assert result["coverage"]["sparse_history"] is False
    assert not any(warning.startswith("Lịch sử thưa:") for warning in result["warnings"])


def test_noisy_history_gives_finite_mae_and_consistent_sample_counts():
    start = datetime(2026, 1, 5)
    rng = random.Random(7)
    counts = {start + timedelta(hours=i): rng.randint(0, 12) for i in range(70 * 24)}
    result = build_forecast(counts, dict(counts), start + timedelta(days=70))
    assert result["status"] == "ready"
    assert math.isfinite(result["backtest"]["mae"]) and result["backtest"]["mae"] >= 0
    assert result["coverage"]["hours_with_departures"] == result["coverage"]["hours_with_arrivals"]
    for row in result["predictions"]:
        at = datetime.fromisoformat(row["at"]).replace(tzinfo=None)
        expected = sum(1 for week in range(1, SEASONAL_WEEKS + 1) if at - timedelta(weeks=week) >= start)
        assert row["samples_observed"] + row["samples_zero_filled"] == expected > 0
        assert row["samples_observed"] >= 0 and row["samples_zero_filled"] >= 0


def test_aware_utc_timestamps_bucket_into_business_local_hour():
    utc = timezone.utc
    arrivals = {datetime(2026, 1, 1, 17, 30, tzinfo=utc): 2,        # 00:30 ngày 02/01 giờ Việt Nam
                datetime(2026, 1, 2, 0, 15): 1,                       # cùng bucket 00:00 ngày 02/01 (naive local)
                datetime(2026, 1, 1, 16, 45, tzinfo=utc): 4}         # 23:45 ngày 01/01 giờ Việt Nam
    result = build_forecast(arrivals, {}, datetime(2026, 1, 9, 0, 0, tzinfo=utc))
    coverage = result["coverage"]
    assert result["as_of"] == "2026-01-09T07:00:00+07:00"
    assert coverage["window_start"] == "2026-01-01T23:00:00+07:00"
    assert coverage["hours_with_arrivals"] == 2 and coverage["days_with_arrivals"] == 2
    assert coverage["hours_in_window"] == 7 * 24 + 8


def test_staff_capacity_is_explicit_and_does_not_hide_unmet_demand():
    data = {"status": "ready", "predictions": [{"at": "2026-01-01T00:00:00+07:00", "arrivals": 100, "departures": 100}]}
    result = build_staff_plan(data, service_seconds=60, utilization=0.8, min_staff=1, max_staff=2)
    plan = result["plan"][0]
    assert plan["staff_required"] == 5 and plan["staff_assigned"] == 2
    assert plan["capacity_shortfall"] == 104
    assert result["assumptions"]["service_seconds_per_vehicle"] == 60
