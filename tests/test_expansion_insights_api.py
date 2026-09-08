"""Site isolation and history-window correctness for deterministic insights."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.clock import business_now
from database import get_db
from expansion.insights_router import router
from expansion.site_models import ParkingSite, SiteMembership
from models.parking_session import ParkingSession
from services.auth_service import get_current_user


@pytest.fixture
def insights(db_session, test_user, zone):
    site, other = ParkingSite(name="Insights site"), ParkingSite(name="Other insights site")
    db_session.add_all([site, other]); db_session.flush()
    zone.site_id = site.id
    db_session.add(SiteMembership(site_id=site.id, user_id=test_user.id, role="staff"))
    db_session.commit()
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(app) as client:
        yield client, db_session, site, other


def test_insights_are_scoped_and_empty_history_stays_empty(insights):
    client, _, site, other = insights
    for resource in ("forecast", "anomalies"):
        assert client.get(f"/api/v2/insights/{resource}", params={"site_id": other.id}).status_code == 403
    response = client.get("/api/v2/insights/forecast", params={"site_id": site.id})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["status"] == "insufficient_data" and response.json()["predictions"] == []
    plan = client.post("/api/v2/insights/staff-plan", json={"site_id": site.id, "service_seconds_per_vehicle": 45})
    assert plan.status_code == 200 and plan.json()["plan"] == []
    assert plan.json()["assumptions"]["measurement_verified"] is False
    measured = client.post("/api/v2/insights/staff-plan", json={"site_id": site.id,
        "service_seconds_per_vehicle": 45, "service_time_source": "measured", "measurement_samples": 2})
    assert measured.status_code == 422


def test_forecast_response_exposes_coverage_transparency_fields(insights):
    client, _, site, _ = insights
    coverage = client.get("/api/v2/insights/forecast", params={"site_id": site.id}).json()["coverage"]
    for key in ("history_days", "required_days", "days_with_arrivals", "hours_in_window", "hours_with_arrivals",
                "hours_with_departures", "hours_zero_filled", "observation_completeness", "completeness_note", "sparse_history"):
        assert key in coverage, key
    assert coverage["observation_completeness"] == "unknown" and coverage["hours_with_arrivals"] == 0
    plan = client.post("/api/v2/insights/staff-plan", json={"site_id": site.id, "service_seconds_per_vehicle": 45}).json()
    assert plan["coverage"]["observation_completeness"] == "unknown"


def test_recent_departure_counts_even_when_arrival_precedes_history_window(insights, vehicle, parking_slot, test_user, monkeypatch):
    client, db, site, _ = insights
    now = business_now().replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr("expansion.insights_router.business_now", lambda: now)
    old_stay = ParkingSession(vehicle_id=vehicle.id, parking_slot_id=parking_slot.id,
        check_in_time=now - timedelta(days=90), check_out_time=now - timedelta(hours=2),
        status="completed", parking_fee=0, staff_in_id=test_user.id, staff_out_id=test_user.id)
    db.add(old_stay); db.commit()
    captured = {}
    def spy(arrivals, departures, at, horizon):
        captured.update(arrivals=arrivals, departures=departures)
        return {"warnings": []}
    monkeypatch.setattr("expansion.insights_router.build_forecast", spy)
    result = client.get("/api/v2/insights/forecast", params={"site_id": site.id})
    assert result.status_code == 200, result.text
    assert captured["departures"][now - timedelta(hours=2)] == 1


def test_long_stay_alert_reports_evidence_without_claiming_fraud(insights, parking_session, monkeypatch):
    client, _, site, _ = insights
    monkeypatch.setattr("expansion.insights_router.business_now", lambda: parking_session.check_in_time + timedelta(hours=30))
    result = client.get("/api/v2/insights/anomalies", params={"site_id": site.id}).json()
    alert = next(item for item in result["items"] if item["code"] == "long_stay")
    assert alert["session_id"] == parking_session.id
    assert alert["evidence"] == {"duration_hours": 30.0, "threshold_hours": 24}
