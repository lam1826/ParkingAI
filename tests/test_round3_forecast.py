from datetime import datetime, timedelta

from expansion.forecast import build_forecast


def test_backtest_compares_three_methods_on_identical_targets():
    now = datetime(2026, 9, 8, 12)
    arrivals = {now - timedelta(hours=h): (h % 24) + 1 for h in range(1, 56 * 24 + 1)}
    result = build_forecast(arrivals, {}, now)
    backtest = result["backtest"]
    assert set(backtest["baselines"]) == {"naive_last_hour", "seasonal_naive", "same_weekday_hour_mean"}
    assert all(value["samples"] == backtest["samples"] for value in backtest["baselines"].values())
    assert backtest["baselines"]["seasonal_naive"]["mae"] == 0
    assert 0 <= backtest["interval_coverage"] <= 1
    assert backtest["interval_samples"] == backtest["samples"]


def test_backtest_does_not_use_future_observations():
    now = datetime(2026, 9, 8, 12)
    arrivals = {now - timedelta(hours=h): h % 9 for h in range(1, 60 * 24 + 1)}
    expected = build_forecast(arrivals, {}, now)
    arrivals[now + timedelta(hours=1)] = 9999999
    assert build_forecast(arrivals, {}, now) == expected
