"""AI boundary regressions: invalid statistics, blank answers and provenance."""
from datetime import datetime
import json

import pytest

from models.ai_report import AiReport
from services.auth_service import AuthService


@pytest.fixture
def headers(test_user):
    token = AuthService().create_access_token(
        user_id=test_user.id, username=test_user.username, role="staff"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def business_reference_now():
    return datetime(2026, 8, 20, 17, 45)


FLOW_CASES = [
    ("/ai/ask", {"question": "Tình hình?", "parking_stats": {"total": 1}}),
    ("/ai/question", {"question": "Tình hình?"}),
    ("/ai/daily-report", {"target_date": "2026-08-25"}),
    ("/ai/weekly-report", {"start_date": "2026-08-19", "end_date": "2026-08-25"}),
    ("/ai/staff-suggestion", {}),
]


@pytest.mark.parametrize("path,payload", FLOW_CASES)
@pytest.mark.parametrize("answer", ["", " \n\t", None, {"content": "invalid"}])
def test_invalid_provider_answer_is_502_and_never_saved(
    client, db_session, headers, mock_ai_provider_client, path, payload, answer
):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = answer
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 502
    assert db_session.query(AiReport).count() == 0


@pytest.mark.parametrize("stats", [
    {"total_vehicles": -1}, {"total_vehicles": "ten"}, {"total_vehicles": True},
    {"revenue": "500000"}, {"occupancy_rate": 101}, {"total_slots": 1.5},
    {"nested": {"total_revenue_today": 500.5}}, {"hourly_traffic": [{"hour": 24, "count": 1}]},
    {"parking_revenue": "25000"}, {"monthly_pass_revenue": -1}, {"refunds": 1.5},
])
def test_invalid_custom_statistics_rejected_before_provider(
    client, headers, mock_ai_provider_client, stats
):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "ok"
    response = client.post("/ai/ask", json={"question": "Phân tích", "parking_stats": stats}, headers=headers)
    assert response.status_code == 422
    mock_ai_provider_client.assert_not_called()


@pytest.mark.parametrize("payload", [
    {"hourly_traffic": [{"time_label": "25:00", "total_vehicles": 1}]},
    {"hourly_traffic": [{"time_label": "08:00", "total_vehicles": -1}]},
    {"hourly_traffic": [{"time_label": "08:00", "total_vehicles": 1}], "revenue": True},
])
def test_staff_invalid_statistics_rejected_before_provider(client, headers, mock_ai_provider_client, payload):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "ok"
    response = client.post("/ai/staff-suggestion", json=payload, headers=headers)
    assert response.status_code == 422
    mock_ai_provider_client.assert_not_called()


def test_weekly_report_includes_hourly_counts_for_exact_requested_period(
    client, db_session, headers, mock_ai_provider_client, parking_session
):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "Giờ 17 đông nhất."
    response = client.post("/ai/weekly-report", json={"start_date": "2026-08-19", "end_date": "2026-08-25"}, headers=headers)
    assert response.status_code == 200
    report = db_session.query(AiReport).one()
    assert '"hourly_traffic"' in report.prompt_used
    assert '"time_label": "17:00"' in report.prompt_used
    assert '"total_vehicles": 1' in report.prompt_used
    metadata = json.loads(report.prompt_used.splitlines()[0].removeprefix("PARKINGAI_CONTEXT "))
    assert metadata == {"source": "database", "start_date": "2026-08-19", "end_date": "2026-08-25"}


def test_custom_report_provenance_does_not_claim_database(client, db_session, headers, mock_ai_provider_client):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "ok"
    response = client.post("/ai/daily-report", json={"target_date": "2026-08-25", "parking_stats": {"total": 1}}, headers=headers)
    assert response.status_code == 200
    metadata = json.loads(db_session.query(AiReport).one().prompt_used.splitlines()[0].removeprefix("PARKINGAI_CONTEXT "))
    assert metadata["source"] == "custom"


def test_refund_period_can_supply_negative_net_revenue(client, headers, mock_ai_provider_client):
    mock_ai_provider_client.return_value.models.generate_content.return_value.text = "Chi hoàn tiền lớn hơn thu trong kỳ."
    response = client.post("/ai/ask", json={"question": "Tóm tắt", "parking_stats": {"total_revenue": -500000, "total_vehicles": 0}}, headers=headers)
    assert response.status_code == 200
