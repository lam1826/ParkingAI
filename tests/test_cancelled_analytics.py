"""A cancelled mistaken admission remains history, not actual traffic."""
from datetime import timedelta

import pytest

from test_expansion_sites import env  # noqa: F401
from models.parking_session import ParkingSession
from services.parking_service import ParkingService
from services.report_service import ReportService


@pytest.fixture
def traffic(env, monkeypatch):
    today = env.now.date()
    start = env.now.replace(hour=8, minute=0, second=0, microsecond=0)
    rows = [ParkingSession(vehicle_id=env.vehicle.id, parking_slot_id=env.slot.id,
                           staff_in_id=env.staff.id, check_in_time=start, status="cancelled")
            for _ in range(2)]
    rows.append(ParkingSession(vehicle_id=env.vehicle.id, parking_slot_id=env.slot.id,
                               staff_in_id=env.staff.id, check_in_time=start + timedelta(hours=1), status="active"))
    env.db.add_all(rows)
    env.slot.is_occupied = True
    env.db.commit()
    monkeypatch.setattr("services.parking_service.business_today", lambda: today)
    return env, today, rows


def test_daily_statistics_ignore_cancelled_admissions_and_false_peak(traffic):
    env, today, _ = traffic
    result = ParkingService(env.db).get_parking_statistics(today)
    assert result["total_vehicles_today"] == 1
    assert result["peak_hour"] == "09:00 - 10:00"


def test_dashboard_counts_actual_traffic_only(traffic):
    env, _, _ = traffic
    result = ParkingService(env.db).get_dashboard_data()
    assert result["total_vehicles_today"] == 1
    assert result["top_peak_hours"] == [{"hour": "09:00 - 10:00", "count": 1}]


def test_legacy_weekly_ai_input_excludes_cancelled_admissions(traffic):
    env, today, _ = traffic
    result = ParkingService(env.db).get_daily_summaries(today, today)
    assert result[0]["total_entries"] == 1
    assert result[0]["total_exits"] == 0


@pytest.mark.parametrize("period", ["day", "week", "month", "year"])
def test_traffic_report_periods_ignore_cancelled_admissions(traffic, period):
    env, today, _ = traffic
    report = ReportService(env.db).get_traffic_report(period, today)
    for bucket in report.values():
        assert sum(row["total_vehicles"] for row in bucket) == 1


def test_recent_history_labels_cancelled_without_removing_it(traffic):
    env, _, rows = traffic
    result = {row["id"]: row for row in ParkingService(env.db).get_recent_sessions()}
    assert len(result) == 3
    assert result[rows[0].id]["status"] == "Đã hủy"
    assert result[rows[2].id]["status"] == "Đang đỗ"


def test_scoped_report_keeps_the_same_traffic_semantics(traffic):
    env, today, _ = traffic
    response = env.client.get(f"/api/v2/sites/{env.a.id}/reports/summary",
                              params={"anchor_date": str(today)})
    assert response.status_code == 200
    assert response.json()["total_arrivals"] == 1
    assert response.json()["peak_hours"] == ["09:00"]
