"""Original assignment journeys stay within the authorized lot; no live provider."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from test_expansion_sites import env  # noqa: F401
from models.role import Role
from services.parking_service import ParkingService


def arrive(env):
    ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id,
        env.staff.id, parking_slot_id=env.slot.id, _expected_site_id=env.a.id)


def root(env):
    return f"/api/v2/sites/{env.a.id}"


def test_site_session_time_filter_excludes_other_days_and_uses_inclusive_dates(env):
    arrive(env)
    day = env.now.date()
    endpoint = root(env) + "/sessions"
    assert len(env.client.get(endpoint, params={"date_from": str(day), "date_to": str(day)}).json()) == 1
    assert env.client.get(endpoint, params={"date_to": str(day - timedelta(days=1))}).json() == []
    assert env.client.get(endpoint, params={"date_from": str(day + timedelta(days=1))}).json() == []
    assert env.client.get(endpoint, params={"date_from": str(day), "date_to": str(day - timedelta(days=1))}).status_code == 422
    assert env.client.get(endpoint, params={"date_to": "9999-12-31"}).status_code == 422


def test_summary_uses_only_site_data_and_reports_current_availability_separately(env):
    arrive(env)
    response = env.client.get(root(env) + "/reports/summary", params={"anchor_date": str(env.now.date())})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["site_id"] == env.a.id and report["total_arrivals"] == 1
    assert report["current_availability"]["occupied"] == 1
    assert report["current_availability"]["as_of"]
    assert sum(row["arrivals"] for row in report["hourly_traffic"]) == 1
    assert report["revenue"]["total_revenue"] == 0
    assert env.vehicle.license_plate not in response.text
    assert env.client.get(f"/api/v2/sites/{env.b.id}/reports/summary").status_code == 403
    env.actor["user"] = env.account
    assert env.client.get(root(env) + "/reports/summary").status_code == 403


@pytest.mark.parametrize("kind", ["report", "question", "staff"])
@pytest.mark.parametrize("period", ["day", "week"])
def test_scoped_ai_grounds_context_and_replays_without_another_provider_call(env, mock_ai_provider_client, kind, period):
    arrive(env)
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "Phân tích từ dữ liệu được cung cấp."
    body = {"kind": kind, "period": period, "anchor_date": str(env.now.date()),
            "question": "Khung giờ nào đông nhất?", "request_id": str(uuid4())}
    endpoint = root(env) + "/ai/analyses"
    result = env.client.post(endpoint, json=body)
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["site_id"] == env.a.id and row["kind"] == kind
    prompt = mock_ai_provider_client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert "PARKING_DATA" in prompt and "QUESTION_JSON" in prompt
    assert '"total_arrivals": 1' in prompt and env.vehicle.license_plate not in prompt
    assert "KHÔNG" in prompt and "giả định" in prompt
    replay = env.client.post(endpoint, json=body)
    assert replay.status_code == 201 and replay.json()["id"] == row["id"]
    assert mock_ai_provider_client.return_value.models.generate_content.call_count == 1
    assert env.client.post(endpoint, json={**body, "period": "week" if period == "day" else "day"}).status_code == 409
    history = env.client.get(endpoint).json()
    assert history[0]["id"] == row["id"] and "prompt_used" not in history[0]
    assert env.client.get(f"/api/v2/sites/{env.b.id}/ai/analyses/{row['id']}").status_code == 403
    env.actor["user"] = env.account
    assert env.client.get(endpoint).status_code == 403


def test_ai_disabled_and_provider_failure_do_not_break_reports_or_save_fake_answers(env, mock_ai_provider_client, monkeypatch):
    from core.config import settings
    body = {"kind": "report", "period": "day", "request_id": str(uuid4())}
    endpoint = root(env) + "/ai/analyses"
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    assert env.client.post(endpoint, json=body).status_code == 503
    mock_ai_provider_client.assert_not_called()
    assert env.client.get(root(env) + "/reports/summary").status_code == 200
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    mock_ai_provider_client.return_value.models.generate_content.side_effect = TimeoutError("PRIVATE_PROVIDER_DETAIL")
    response = env.client.post(endpoint, json=body)
    assert response.status_code == 504 and "PRIVATE_PROVIDER_DETAIL" not in response.text
    assert env.client.get(endpoint).json() == []


def test_staff_can_use_core_analytics_and_revoked_role_cannot(env):
    role = env.db.scalar(select(Role).where(Role.name == "staff"))
    if role is None:
        role = Role(name="staff"); env.db.add(role)
    env.staff.role = role; env.db.commit()
    assert env.client.get(root(env) + "/reports/summary").status_code == 200
    env.staff.role = env.account.role; env.db.commit()
    assert env.client.get(root(env) + "/reports/summary").status_code == 403


@pytest.mark.parametrize("extra", [{"site_id": 999}, {"parking_stats": {"total_arrivals": 999}}, {"question": "   ", "kind": "question"}, {"anchor_date": "9999-12-31"}])
def test_ai_rejects_client_statistics_and_invalid_input(env, mock_ai_provider_client, extra):
    response = env.client.post(root(env) + "/ai/analyses", json={"kind": "report", "request_id": str(uuid4()), **extra})
    assert response.status_code == 422, response.text
    mock_ai_provider_client.assert_not_called()


def test_other_site_traffic_and_unassigned_history_do_not_enter_context(env):
    from expansion.site_models import SiteMembership
    from models.zone import Zone
    from models.parking_slot import ParkingSlot
    arrive(env)
    zone = Zone(name="Private B", capacity=1, site_id=env.b.id)
    env.db.add(zone); env.db.flush()
    slot = ParkingSlot(slot_name="B-PRIVATE", zone_id=zone.id, vehicle_type_id=env.other.vehicle_type_id)
    membership = SiteMembership(site_id=env.b.id, user_id=env.staff.id, role="manager")
    env.db.add_all([slot, membership]); env.db.commit()
    ParkingService(env.db).check_in(env.other.license_plate, env.other.vehicle_type_id,
        env.staff.id, parking_slot_id=slot.id, _expected_site_id=env.b.id)
    env.db.delete(membership); env.db.commit()
    result = env.client.get(root(env) + "/reports/summary", params={"anchor_date": str(env.now.date())}).json()
    assert result["total_arrivals"] == 1
    assert "Private B" not in str(result) and env.other.license_plate not in str(result)


def test_access_revoked_while_provider_runs_is_rechecked_before_saving(env, mock_ai_provider_client):
    from expansion.analytics_models import SiteAiAnalysis
    from expansion.site_models import SiteMembership
    def revoke(**kwargs):
        membership = env.db.scalar(select(SiteMembership).where(SiteMembership.user_id == env.staff.id))
        env.db.delete(membership); env.db.commit()
        from types import SimpleNamespace
        return SimpleNamespace(text="Không được gửi kết quả này sau khi mất quyền.")
    mock_ai_provider_client.return_value.models.generate_content.side_effect = revoke
    response = env.client.post(root(env) + "/ai/analyses", json={"kind": "report", "request_id": str(uuid4())})
    assert response.status_code == 403
    assert env.db.scalars(select(SiteAiAnalysis)).all() == []


def test_summary_revenue_matches_ledger_after_receipt_and_refund(env, monkeypatch):
    from models.payment import Payment
    arrive(env)
    from models.parking_session import ParkingSession
    session = env.db.scalar(select(ParkingSession))
    env.clock["now"] += timedelta(hours=1)
    endpoint = root(env) + f"/sessions/{session.id}"
    quote = env.client.get(endpoint + "/checkout-quote")
    assert quote.status_code == 200, quote.text
    response = env.client.put(endpoint + "/check-out", json={"quote_token": quote.json()["quote_token"], "payment_confirmed": True, "payment_method": "cash"})
    assert response.status_code == 200, response.text
    receipt = env.db.scalar(select(Payment).where(Payment.kind == "receipt"))
    assert receipt.amount > 0
    import services.payment_service as payment_service
    monkeypatch.setattr(payment_service, "business_now", lambda: receipt.created_at)
    response = env.client.post(root(env) + f"/payments/{receipt.id}/refund", json={"amount": receipt.amount, "reason": "Hoàn thử trong test riêng", "idempotency_key": str(uuid4())})
    assert response.status_code == 200, response.text
    result = env.client.get(root(env) + "/reports/summary", params={"anchor_date": str(receipt.created_at.date())}).json()
    assert result["revenue"]["parking_revenue"] == receipt.amount
    assert result["revenue"]["refunds"] == receipt.amount
    assert result["revenue"]["total_revenue"] == 0
