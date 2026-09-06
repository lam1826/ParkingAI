"""Prepaid consecutive card periods cover a stay without retroactive renewal."""
from checkout_helpers import quote_confirmation, service_confirmation

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from crud import parking_session as session_crud
from models.parking_session import ParkingSession
from schemas.monthly_pass import MonthlyPassCreate, MonthlyPassRenew
from services.auth_service import AuthService
from services.monthly_subscription_service import create_subscription, renew_subscription


def _headers(user):
    return {"Authorization": "Bearer " + AuthService().create_access_token(user_id=user.id, username=user.username, role=user.role.name)}


@pytest.fixture
def coverage_setup(db_session, test_user, vehicle, customer, parking_slot, price_config, business_reference_now):
    today = business_reference_now.date()
    original = create_subscription(db_session, MonthlyPassCreate(
        customer_id=customer.id, vehicle_id=vehicle.id, pass_code="COVERAGE-CARD-1", price=500_000,
        start_date=today-timedelta(days=29), end_date=today,
    ), test_user.id)
    return original, datetime.combine(today, time(23)), today + timedelta(days=30)


def _renew(db, original, actor, end, *, start=None, request_id="coverage-renewal-before-entry"):
    return renew_subscription(db, original.id, MonthlyPassRenew(
        start_date=start or original.end_date+timedelta(days=1), end_date=end,
        price=500_000, request_id=request_id,
    ), actor.id)


def _check_in(client, db, user, vehicle, slot, endpoint):
    payload = ({"vehicle_id": vehicle.id, "parking_slot_id": slot.id} if endpoint.startswith("/api")
               else {"license_plate": vehicle.license_plate, "vehicle_type_id": vehicle.vehicle_type_id, "parking_slot_id": slot.id})
    response = client.post(endpoint, json=payload, headers=_headers(user))
    assert response.status_code == 201, response.text
    body = response.json()
    return db.get(ParkingSession, body.get("session_id") or body["id"])


@pytest.mark.parametrize("endpoint", ["/api/v1/parking-sessions/check-in", "/parking/check-in"])
def test_prepaid_contiguous_renewal_covers_stay_across_period_boundary(
    client, db_session, test_user, vehicle, parking_slot, coverage_setup, monkeypatch, endpoint,
):
    original, entered_at, end = coverage_setup
    _renew(db_session, original, test_user, end)
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, endpoint)
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at + timedelta(hours=2))
    confirmation = quote_confirmation(client, _headers(test_user), session.id)
    response = client.put(f"/api/v1/parking-sessions/{session.id}/check-out", headers=_headers(test_user), json=confirmation)
    assert response.status_code == 200, response.text
    assert response.json()["parking_fee"] == 0
    assert session.monthly_coverage_end == end


def test_renewal_after_admission_does_not_extend_existing_session(
    client, db_session, test_user, vehicle, parking_slot, price_config, coverage_setup, monkeypatch,
):
    original, entered_at, end = coverage_setup
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, "/api/v1/parking-sessions/check-in")
    _renew(db_session, original, test_user, end, request_id="coverage-renewal-after-entry")
    assert session.monthly_coverage_end == original.end_date
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at+timedelta(hours=2))
    confirmation = quote_confirmation(client, _headers(test_user), session.id)
    response = client.put(f"/api/v1/parking-sessions/{session.id}/check-out", headers=_headers(test_user), json=confirmation)
    assert response.status_code == 200, response.text
    assert response.json()["parking_fee"] == 2 * price_config.price


def test_cancelling_next_period_after_admission_keeps_frozen_coverage(
    client, db_session, test_user, vehicle, parking_slot, coverage_setup, monkeypatch,
):
    original, entered_at, end = coverage_setup
    renewed = _renew(db_session, original, test_user, end)
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, "/parking/check-in")
    response = client.put(f"/api/v1/monthly-passes/{renewed.id}", json={"is_active": False}, headers=_headers(test_user))
    assert response.status_code == 200, response.text
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at+timedelta(hours=2))
    confirmation = quote_confirmation(client, _headers(test_user), session.id)
    response = client.post("/parking/check-out", json={**{"license_plate": vehicle.license_plate}, **confirmation}, headers=_headers(test_user))
    assert response.status_code == 200, response.text
    assert response.json()["parking_fee"] == 0
    assert session.monthly_coverage_end == end


@pytest.mark.parametrize("ineligible", ["gap", "cancelled", "different_card"])
def test_admission_does_not_join_ineligible_periods(
    client, db_session, test_user, vehicle, customer, parking_slot, price_config, coverage_setup, monkeypatch, ineligible,
):
    original, entered_at, end = coverage_setup
    if ineligible == "different_card":
        create_subscription(db_session, MonthlyPassCreate(
            customer_id=customer.id, vehicle_id=vehicle.id, pass_code="DIFFERENT-CARD", price=500_000,
            start_date=original.end_date+timedelta(days=1), end_date=end,
        ), test_user.id)
    else:
        next_period = _renew(db_session, original, test_user, end,
                             start=original.end_date+timedelta(days=2 if ineligible == "gap" else 1))
        if ineligible == "cancelled":
            next_period.is_active = False
            db_session.commit()
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, "/parking/check-in")
    assert session.monthly_coverage_end == original.end_date
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at+timedelta(hours=2))
    confirmation = quote_confirmation(client, _headers(test_user), session.id)
    response = client.put(f"/api/v1/parking-sessions/{session.id}/check-out", headers=_headers(test_user), json=confirmation)
    assert response.status_code == 200, response.text
    assert response.json()["parking_fee"] == 2 * price_config.price


def test_admission_joins_multiple_contiguous_prepaid_periods(
    client, db_session, test_user, vehicle, parking_slot, coverage_setup, monkeypatch,
):
    original, entered_at, end = coverage_setup
    second = _renew(db_session, original, test_user, end)
    third = _renew(db_session, second, test_user, end+timedelta(days=30), request_id="coverage-third-prepaid-period")
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, "/api/v1/parking-sessions/check-in")
    assert session.monthly_coverage_end == third.end_date


def test_exit_after_frozen_coverage_keeps_existing_full_stay_rate_policy(
    client, db_session, test_user, vehicle, parking_slot, price_config, coverage_setup, monkeypatch,
):
    original, entered_at, end = coverage_setup
    _renew(db_session, original, test_user, end)
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, "/parking/check-in")
    left_at = datetime.combine(end+timedelta(days=1), time(1))
    monkeypatch.setattr(session_crud, "server_now", lambda: left_at)
    confirmation = quote_confirmation(client, _headers(test_user), session.id)
    response = client.put(f"/api/v1/parking-sessions/{session.id}/check-out", headers=_headers(test_user), json=confirmation)
    assert response.status_code == 200, response.text
    assert response.json()["parking_fee"] == (30 * 24 + 2) * price_config.price


@pytest.mark.parametrize("endpoint", ["/api/v1/parking-sessions/check-in", "/parking/check-in"])
def test_client_cannot_choose_coverage_end_at_admission(client, db_session, test_user, vehicle, parking_slot, price_config, endpoint):
    payload = ({"vehicle_id": vehicle.id} if endpoint.startswith("/api") else
               {"license_plate": vehicle.license_plate, "vehicle_type_id": vehicle.vehicle_type_id, "parking_slot_id": parking_slot.id})
    response = client.post(endpoint, json={**payload, "monthly_coverage_end": "2099-12-31"}, headers=_headers(test_user))
    assert response.status_code == 422, response.text
    assert db_session.query(ParkingSession).count() == 0


def test_client_cannot_rewrite_coverage_on_exit(client, db_session, test_user, vehicle, parking_slot, coverage_setup, monkeypatch):
    _, entered_at, _ = coverage_setup
    monkeypatch.setattr(session_crud, "server_now", lambda: entered_at)
    session = _check_in(client, db_session, test_user, vehicle, parking_slot, "/api/v1/parking-sessions/check-in")
    for path, payload in ((f"/api/v1/parking-sessions/{session.id}/check-out", {}), ("/parking/check-out", {"license_plate": vehicle.license_plate})):
        response = (client.put if path.startswith("/api") else client.post)(path, json={**payload, "monthly_coverage_end": "2099-12-31"}, headers=_headers(test_user))
        assert response.status_code == 422, response.text
    db_session.refresh(session)
    assert session.status == "active"


@pytest.mark.parametrize("legacy", [True, False])
def test_database_freezes_coverage_even_for_legacy_null(
    db_session, test_user, vehicle, coverage_setup, legacy,
):
    original, entered_at, end = coverage_setup
    session = ParkingSession(vehicle_id=vehicle.id, monthly_pass_id=original.id,
                             monthly_coverage_end=None if legacy else original.end_date,
                             check_in_time=entered_at, staff_in_id=test_user.id, status="active")
    db_session.add(session)
    db_session.commit()
    with pytest.raises(IntegrityError, match="coverage.*immutable"):
        db_session.execute(text("UPDATE parking_sessions SET monthly_coverage_end = :end WHERE id = :id"),
                           {"end": end.isoformat(), "id": session.id})
    db_session.rollback()
