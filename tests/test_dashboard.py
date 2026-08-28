import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from models.user import User
from services.auth_service import AuthService


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Fixture tạo Authentication Header (Bearer Token) cho test user."""
    auth_service = AuthService()
    token = auth_service.create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=str(test_user.role)
    )
    return {"Authorization": f"Bearer {token}"}


@patch("services.parking_service.ParkingService.get_dashboard_data")
def test_get_dashboard_success(mock_get_dashboard, client: TestClient, auth_headers: dict):
    """1. Kiểm thử lấy thông tin dashboard thành công (Trả về đầy đủ cấu trúc dữ liệu)."""
    mock_get_dashboard.return_value = {
        "total_vehicles_today": 45,
        "total_revenue_today": 1500000.0,
        "vehicles_currently_inside": 12,
        "vehicles_checked_out_today": 33,
        "occupancy_rate_percentage": 75.5,
        "top_peak_hours": [{"hour": "08:00 - 09:00", "count": 10}]
    }

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "total_vehicles_today" in data
    assert "total_revenue_today" in data
    assert "occupancy_rate_percentage" in data
    assert "top_peak_hours" in data


@patch("services.parking_service.ParkingService.get_dashboard_data")
def test_dashboard_total_vehicles(mock_get_dashboard, client: TestClient, auth_headers: dict):
    """2. Kiểm thử chỉ số Tổng xe (total_vehicles_today) trên Dashboard."""
    mock_get_dashboard.return_value = {
        "total_vehicles_today": 30,
        "total_revenue_today": 500000.0,
        "vehicles_currently_inside": 5,
        "vehicles_checked_out_today": 25,
        "occupancy_rate_percentage": 50.0,
        "top_peak_hours": [{"hour": "17:00 - 18:00", "count": 8}]
    }

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_vehicles_today"] == 30


@patch("services.parking_service.ParkingService.get_dashboard_data")
def test_dashboard_revenue(mock_get_dashboard, client: TestClient, auth_headers: dict):
    """3. Kiểm thử chỉ số Doanh thu (total_revenue_today) trên Dashboard."""
    mock_get_dashboard.return_value = {
        "total_vehicles_today": 20,
        "total_revenue_today": 2500000.0,
        "vehicles_currently_inside": 4,
        "vehicles_checked_out_today": 16,
        "occupancy_rate_percentage": 40.0,
        "top_peak_hours": [{"hour": "12:00 - 13:00", "count": 6}]
    }

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total_revenue_today"] == 2500000.0


@patch("services.parking_service.ParkingService.get_dashboard_data")
def test_dashboard_occupancy_rate(mock_get_dashboard, client: TestClient, auth_headers: dict):
    """4. Kiểm thử chỉ số Tỷ lệ lấp đầy (occupancy_rate_percentage) trên Dashboard."""
    mock_get_dashboard.return_value = {
        "total_vehicles_today": 40,
        "total_revenue_today": 1000000.0,
        "vehicles_currently_inside": 32,
        "vehicles_checked_out_today": 8,
        "occupancy_rate_percentage": 80.0,
        "top_peak_hours": [{"hour": "09:00 - 10:00", "count": 9}]
    }

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["occupancy_rate_percentage"] == 80.0


@patch("services.parking_service.ParkingService.get_dashboard_data")
def test_dashboard_peak_hours(mock_get_dashboard, client: TestClient, auth_headers: dict):
    """5. Kiểm thử chỉ số Giờ cao điểm (top_peak_hours) trên Dashboard."""
    mock_get_dashboard.return_value = {
        "total_vehicles_today": 25,
        "total_revenue_today": 800000.0,
        "vehicles_currently_inside": 10,
        "vehicles_checked_out_today": 15,
        "occupancy_rate_percentage": 60.0,
        "top_peak_hours": [{"hour": "08:00 - 09:00", "count": 12}]
    }

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["top_peak_hours"][0]["hour"] == "08:00 - 09:00"


def test_dashboard_suggestion_openapi_documents_rule_based_provenance(
    client: TestClient,
):
    """Endpoint legacy /ai-insight không gọi provider; OpenAPI phải mô tả
    đúng đây là gợi ý rule-based, không gắn nhãn Gemini/AI."""
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/dashboard/ai-insight"]["get"]
    field_description = openapi["components"]["schemas"]["AIInsightResponse"][
        "properties"
    ]["insight"]["description"]
    documentation = " ".join(
        [operation["summary"], operation.get("description", ""), field_description]
    )

    assert "quy tắc" in documentation.lower()
    assert "không gọi ai provider" in documentation.lower()
    assert re.search(r"AI Insight|Gemini", documentation, flags=re.IGNORECASE) is None
