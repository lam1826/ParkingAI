from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors

from models.user import User
from services.auth_service import AuthService


@pytest.fixture
def ai_auth_headers(test_user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=test_user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


AI_FLOW_CASES = [
    (
        "/ai/daily-report",
        {"target_date": "2026-08-25", "parking_stats": {"total_vehicles": 1}},
    ),
    (
        "/ai/weekly-report",
        {
            "start_date": "2026-08-19",
            "end_date": "2026-08-25",
            "weekly_data": [{"time_label": "2026-08-25", "total_vehicles": 1}],
        },
    ),
    (
        "/ai/ask",
        {"question": "Khung giờ nào đông nhất?", "parking_stats": {"total": 1}},
    ),
    ("/ai/question", {"question": "Khu vực nào còn chỗ?"}),
    (
        "/ai/staff-suggestion",
        {
            "hourly_traffic": [{"time_label": "08:00", "total_vehicles": 1}],
            "revenue": 25000,
            "occupancy_rate": 10,
        },
    ),
]


@pytest.mark.parametrize(("path", "payload"), AI_FLOW_CASES)
@patch("services.ai_service.genai.Client")
def test_all_ai_flows_map_provider_timeout_to_504(
    provider_factory: MagicMock,
    client: TestClient,
    ai_auth_headers: dict[str, str],
    path: str,
    payload: dict,
) -> None:
    provider_factory.return_value.models.generate_content.side_effect = TimeoutError(
        "provider timed out"
    )

    response = client.post(path, json=payload, headers=ai_auth_headers)

    assert response.status_code == 504
    assert "quá thời gian" in response.json()["detail"]
    assert "provider timed out" not in response.text


@pytest.mark.parametrize(("path", "payload"), AI_FLOW_CASES)
@patch("services.ai_service.genai.Client")
def test_all_ai_flows_map_provider_network_failure_to_503(
    provider_factory: MagicMock,
    client: TestClient,
    ai_auth_headers: dict[str, str],
    path: str,
    payload: dict,
) -> None:
    provider_factory.return_value.models.generate_content.side_effect = ConnectionError(
        "network is down"
    )

    response = client.post(path, json=payload, headers=ai_auth_headers)

    assert response.status_code == 503
    assert "tạm thời không khả dụng" in response.json()["detail"]
    assert "network is down" not in response.text


@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    [
        (
            genai_errors.ClientError(
                429,
                {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}},
            ),
            503,
        ),
        (
            genai_errors.ServerError(
                500,
                {"error": {"status": "INTERNAL", "message": "upstream"}},
            ),
            502,
        ),
    ],
)
@patch("services.ai_service.genai.Client")
def test_provider_api_failures_use_gateway_or_availability_status(
    provider_factory: MagicMock,
    client: TestClient,
    ai_auth_headers: dict[str, str],
    provider_error: Exception,
    expected_status: int,
) -> None:
    provider_factory.return_value.models.generate_content.side_effect = provider_error

    response = client.post(
        "/ai/ask",
        json={"question": "Phân tích", "parking_stats": {"total": 1}},
        headers=ai_auth_headers,
    )

    assert response.status_code == expected_status
    assert "quota" not in response.text
    assert "upstream" not in response.text


@pytest.mark.parametrize(("path", "payload"), AI_FLOW_CASES)
@patch("services.ai_service.genai.Client")
def test_ai_flow_outer_handlers_preserve_http_exception(
    provider_factory: MagicMock,
    client: TestClient,
    ai_auth_headers: dict[str, str],
    path: str,
    payload: dict,
) -> None:
    provider_factory.return_value.models.generate_content.side_effect = HTTPException(
        status_code=409,
        detail="provider seam sentinel",
    )

    response = client.post(path, json=payload, headers=ai_auth_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "provider seam sentinel"


def test_unmocked_valid_ai_request_is_blocked_before_provider_instantiation(
    client: TestClient,
    ai_auth_headers: dict[str, str],
) -> None:
    with pytest.raises(
        AssertionError,
        match="Live AI provider access is forbidden during pytest",
    ):
        client.post(
            "/ai/ask",
            json={"question": "Phân tích", "parking_stats": {"total": 1}},
            headers=ai_auth_headers,
        )
