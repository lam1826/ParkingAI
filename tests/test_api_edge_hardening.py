from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.parking_session import ParkingSession
from models.user import User
from services.auth_service import AuthService


@pytest.fixture
def staff_headers(test_user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=test_user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def manager_headers(db_session: Session, test_user: User) -> dict[str, str]:
    test_user.role.name = "manager"
    db_session.commit()
    token = AuthService().create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=test_user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2026-08-03", "2026-08-07"),
        ("2026-08-03", "2026-08-10"),
    ],
)
@patch("routers.ai_report.ParkingService.get_daily_summaries")
@patch("services.ai_service.genai.Client")
def test_weekly_ai_requires_exactly_seven_inclusive_days_before_work(
    mock_genai_client,
    mock_get_daily_summaries,
    client: TestClient,
    staff_headers: dict[str, str],
    start_date: str,
    end_date: str,
):
    response = client.post(
        "/ai/weekly-report",
        headers=staff_headers,
        json={"start_date": start_date, "end_date": end_date},
    )

    assert response.status_code == 422
    mock_get_daily_summaries.assert_not_called()
    mock_genai_client.assert_not_called()


@patch("services.ai_service.genai.Client")
def test_weekly_ai_accepts_exactly_seven_inclusive_days(
    mock_genai_client,
    client: TestClient,
    staff_headers: dict[str, str],
):
    provider = MagicMock()
    provider.models.generate_content.return_value.text = "Báo cáo tuần mock"
    mock_genai_client.return_value = provider

    response = client.post(
        "/ai/weekly-report",
        headers=staff_headers,
        json={
            "start_date": "2026-08-03",
            "end_date": "2026-08-09",
            "weekly_data": [{"date": f"2026-08-{day:02d}"} for day in range(3, 10)],
        },
    )

    assert response.status_code == 200, response.text
    provider.models.generate_content.assert_called_once()


@pytest.mark.parametrize("path", ["/ai/ask", "/ai/question"])
@patch("services.ai_service.genai.Client")
def test_ai_question_length_is_bounded_before_provider(
    mock_genai_client,
    client: TestClient,
    staff_headers: dict[str, str],
    path: str,
):
    payload = {"question": "x" * 1001}
    if path == "/ai/ask":
        payload["parking_stats"] = {"total": 1}

    response = client.post(path, headers=staff_headers, json=payload)

    assert response.status_code == 422
    mock_genai_client.assert_not_called()


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/ai/daily-report",
            {
                "target_date": "2026-08-03",
                "parking_stats": {f"key_{index}": index for index in range(101)},
            },
        ),
        (
            "/ai/weekly-report",
            {
                "start_date": "2026-08-03",
                "end_date": "2026-08-09",
                "weekly_data": [{"date": index} for index in range(8)],
            },
        ),
        (
            "/ai/staff-suggestion",
            {
                "hourly_traffic": [{"hour": index} for index in range(25)],
                "revenue": 0,
                "occupancy_rate": 0,
            },
        ),
    ],
)
@patch("services.ai_service.genai.Client")
def test_ai_custom_collection_item_counts_are_bounded_before_provider(
    mock_genai_client,
    client: TestClient,
    staff_headers: dict[str, str],
    path: str,
    payload: dict,
):
    response = client.post(path, headers=staff_headers, json=payload)

    assert response.status_code == 422
    mock_genai_client.assert_not_called()


@patch("services.ai_service.genai.Client")
def test_ai_custom_payload_serialized_size_is_bounded_before_provider(
    mock_genai_client,
    client: TestClient,
    staff_headers: dict[str, str],
):
    response = client.post(
        "/ai/daily-report",
        headers=staff_headers,
        json={
            "target_date": "2026-08-03",
            "parking_stats": {"nested": {"text": "x" * 33_000}},
        },
    )

    assert response.status_code == 422
    mock_genai_client.assert_not_called()


@patch("services.ai_service.genai.Client")
def test_current_daily_ai_stats_keep_slot_state_with_provenance(
    mock_genai_client,
    client: TestClient,
    staff_headers: dict[str, str],
    parking_slot,
    business_reference_now: datetime,
    monkeypatch,
):
    import core.clock as clock_module

    fixed_instant = business_reference_now.replace(tzinfo=clock_module.BUSINESS_TZ)

    class FixedBusinessClock(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_instant.replace(tzinfo=None)
            return fixed_instant.astimezone(tz)

    monkeypatch.setattr(clock_module, "datetime", FixedBusinessClock)
    provider = MagicMock()
    provider.models.generate_content.return_value.text = "Báo cáo hiện tại mock"
    mock_genai_client.return_value = provider
    target_date = business_reference_now.date().isoformat()

    response = client.post(
        "/ai/daily-report",
        headers=staff_headers,
        json={"target_date": target_date},
    )

    assert response.status_code == 200, response.text
    prompt = provider.models.generate_content.call_args.kwargs["contents"]
    assert '"available_slots": 1' in prompt
    assert '"occupied_slots": 0' in prompt
    assert f'"slot_state_as_of": "{target_date}"' in prompt


@pytest.mark.parametrize(
    "params",
    [
        {"skip": -1},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_ai_report_pagination_is_bounded(
    client: TestClient,
    staff_headers: dict[str, str],
    params: dict,
):
    response = client.get("/ai/reports", headers=staff_headers, params=params)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/ai/daily-report", {"target_date": "2026-08-03"}),
        (
            "/ai/weekly-report",
            {"start_date": "2026-08-03", "end_date": "2026-08-09"},
        ),
        ("/ai/ask", {"question": "Có bao nhiêu xe?", "parking_stats": {"total": 1}}),
        ("/ai/question", {"question": "Có bao nhiêu xe?"}),
        (
            "/ai/staff-suggestion",
            {"hourly_traffic": [{"hour": 8}], "revenue": 0, "occupancy_rate": 0},
        ),
    ],
)
@patch("services.ai_service.genai.Client")
def test_ai_request_models_forbid_unknown_fields_before_provider(
    mock_genai_client,
    client: TestClient,
    staff_headers: dict[str, str],
    path: str,
    payload: dict,
):
    response = client.post(
        path,
        headers=staff_headers,
        json={**payload, "unexpected_server_controlled_field": True},
    )

    assert response.status_code == 422
    mock_genai_client.assert_not_called()


def test_parking_search_normalizes_aware_query_times_to_business_local_naive(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    test_user,
    vehicle,
    parking_slot,
    price_config,
):
    price_config.effective_date = datetime(2026, 8, 24).date()
    db_session.commit()
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        check_in_time=datetime(2026, 8, 25, 0, 30),
        status="active",
        staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(parking_session)
    db_session.commit()

    response = client.get(
        "/parking/search",
        headers=staff_headers,
        params={
            "date_from": "2026-08-24T17:00:00Z",
            "date_to": "2026-08-24T18:00:00Z",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["session_id"] == parking_session.id


def test_parking_search_rejects_reversed_datetime_range(
    client: TestClient,
    staff_headers: dict[str, str],
):
    response = client.get(
        "/parking/search",
        headers=staff_headers,
        params={
            "date_from": "2026-08-25T10:00:00+07:00",
            "date_to": "2026-08-25T09:59:59+07:00",
        },
    )

    assert response.status_code == 422


def test_parking_search_keeps_public_status_query_alias(
    client: TestClient,
    staff_headers: dict[str, str],
    parking_session,
):
    response = client.get(
        "/parking/search",
        headers=staff_headers,
        params={"status": "active"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1


def test_parking_search_supports_cancelled_status(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    test_user,
    vehicle,
):
    cancelled = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=None,
        check_in_time=datetime(2026, 8, 25, 8, 0),
        status="cancelled",
        staff_in_id=test_user.id,
    )
    db_session.add(cancelled)
    db_session.commit()

    response = client.get(
        "/parking/search",
        headers=staff_headers,
        params={"status": "cancelled"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["status"] == "cancelled"


def test_parking_search_returns_persisted_stay_duration(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    test_user,
    vehicle,
):
    completed = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=None,
        check_in_time=datetime(2026, 8, 25, 8, 0),
        check_out_time=datetime(2026, 8, 25, 10, 30),
        parking_fee=50_000,
        status="completed",
        staff_in_id=test_user.id,
        staff_out_id=test_user.id,
    )
    db_session.add(completed)
    db_session.commit()

    response = client.get(
        "/parking/search",
        headers=staff_headers,
        params={"status": "completed"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["duration_minutes"] == 150


@pytest.mark.parametrize(
    ("query_name", "query_value"),
    [
        ("status", "pending"),
        ("sort_by", "vehicle_id"),
    ],
)
def test_parking_search_rejects_unknown_status_and_sort_field(
    client: TestClient,
    staff_headers: dict[str, str],
    query_name: str,
    query_value: str,
):
    response = client.get(
        "/parking/search",
        headers=staff_headers,
        params={query_name: query_value},
    )

    assert response.status_code == 422


def test_parking_search_openapi_documents_status_and_sort_enums(
    client: TestClient,
):
    operation = client.get("/openapi.json").json()["paths"]["/parking/search"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    status_schema = parameters["status"]["schema"]
    status_enum = status_schema.get("enum") or next(
        branch["enum"]
        for branch in status_schema.get("anyOf", [])
        if "enum" in branch
    )
    assert status_enum == ["active", "completed", "cancelled"]
    assert parameters["sort_by"]["schema"]["enum"] == [
        "check_in_time",
        "check_out_time",
        "parking_fee",
    ]


MANAGEMENT_COLLECTION_PATHS = [
    "/api/v1/vehicles",
    "/api/v1/zones",
    "/api/v1/vehicle-types",
    "/api/v1/customers",
    "/api/v1/monthly-passes",
    "/api/v1/parking-slots",
    "/api/v1/parking-sessions",
    "/api/v1/price-configs",
    "/api/v1/roles",
    "/api/v1/users",
]


@pytest.mark.parametrize("path", MANAGEMENT_COLLECTION_PATHS)
@pytest.mark.parametrize("params", [{"skip": -1}, {"limit": 0}, {"limit": 101}])
def test_management_collection_pagination_rejects_out_of_range_values(
    client: TestClient,
    manager_headers: dict[str, str],
    path: str,
    params: dict[str, int],
):
    response = client.get(path, headers=manager_headers, params=params)

    assert response.status_code == 422, (path, params, response.text)


@pytest.mark.parametrize("path", MANAGEMENT_COLLECTION_PATHS)
def test_management_collection_openapi_documents_uniform_pagination_bounds(
    client: TestClient,
    path: str,
):
    operation = client.get("/openapi.json").json()["paths"][path]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}

    assert parameters["skip"]["schema"]["minimum"] == 0
    assert parameters["limit"]["schema"]["minimum"] == 1
    assert parameters["limit"]["schema"]["maximum"] == 100


def test_audit_classifies_parking_session_check_in_as_domain_action(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    vehicle,
    price_config,
):
    path = "/api/v1/parking-sessions/check-in"
    response = client.post(
        path,
        headers=staff_headers,
        json={"vehicle_id": vehicle.id, "parking_slot_id": None},
    )

    assert response.status_code == 201, response.text
    audit = db_session.query(AuditLog).filter(AuditLog.path == path).one()
    assert audit.action == "CHECK_IN"
    assert audit.resource == "parking-sessions"


def test_audit_classifies_parking_session_id_check_out_as_domain_action(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    parking_session,
    price_config,
):
    path = f"/api/v1/parking-sessions/{parking_session.id}/check-out"
    response = client.put(path, headers=staff_headers, json={})

    assert response.status_code == 200, response.text
    audit = db_session.query(AuditLog).filter(AuditLog.path == path).one()
    assert audit.action == "CHECK_OUT"
    assert audit.resource == "parking-sessions"
    assert audit.resource_id == parking_session.id


def test_audit_keeps_legacy_parking_check_in_domain_action(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    vehicle,
    parking_slot,
    price_config,
):
    path = "/parking/check-in"
    response = client.post(
        path,
        headers=staff_headers,
        json={
            "license_plate": vehicle.license_plate,
            "vehicle_type_id": vehicle.vehicle_type_id,
        },
    )

    assert response.status_code == 201, response.text
    audit = db_session.query(AuditLog).filter(AuditLog.path == path).one()
    assert audit.action == "CHECK_IN"


def test_audit_keeps_legacy_parking_check_out_domain_action(
    client: TestClient,
    db_session: Session,
    staff_headers: dict[str, str],
    parking_session,
    price_config,
):
    path = "/parking/check-out"
    response = client.post(
        path,
        headers=staff_headers,
        json={"license_plate": parking_session.vehicle.license_plate},
    )

    assert response.status_code == 200, response.text
    audit = db_session.query(AuditLog).filter(AuditLog.path == path).one()
    assert audit.action == "CHECK_OUT"
