import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from models.user import User
from services.auth_service import AuthService


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Fixture tạo Authentication Header (Bearer Token) cho test user có quyền gọi AI."""
    auth_service = AuthService()
    token = auth_service.create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=str(test_user.role)
    )
    return {"Authorization": f"Bearer {token}"}


@patch("services.ai_service.genai.Client")
def test_ai_question_valid_prompt(mock_genai_client, client: TestClient, auth_headers: dict):
    """1. Kiểm thử POST /ai/question với prompt và dữ liệu hợp lệ (Mock Gemini trả về kết quả chuẩn)."""
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Tổng số xe đang đỗ trong bãi là 15 chiếc."
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_client.return_value = mock_instance

    payload = {
        "question": "Có bao nhiêu xe đang ở trong bãi?",
        "parking_stats": {"active_sessions": 15, "total_slots": 50}
    }
    
    response = client.post("/ai/ask", json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "15 chiếc" in str(data)


def test_ai_question_empty_prompt(client: TestClient, auth_headers: dict):
    """2. Kiểm thử POST /ai/question khi để trống prompt (Pydantic validation bắt lỗi 422)."""
    payload = {
        "question": "",
        "parking_stats": {"active_sessions": 5}
    }
    
    response = client.post("/ai/ask", json=payload, headers=auth_headers)
    
    # Tùy thuộc vào schema có validate min_length hay không, nếu có hoặc bắt buộc -> 422 hoặc 400
    assert response.status_code in [400, 422]


def test_ai_question_empty_data(client: TestClient, auth_headers: dict):
    """3. Kiểm thử POST /ai/ask từ chối dữ liệu rỗng trước khi gọi Gemini."""
    payload = {
        "question": "Doanh thu hôm nay là bao nhiêu?",
        "parking_stats": {}  # Dữ liệu rỗng
    }
    
    response = client.post("/ai/ask", json=payload, headers=auth_headers)
    
    assert response.status_code == 422


@patch("services.ai_service.genai.Client")
def test_ai_gemini_returns_error(mock_genai_client, client: TestClient, auth_headers: dict):
    """4. Kiểm thử khi dịch vụ Gemini API trả về lỗi (Exception từ phía AI Provider)."""
    mock_instance = MagicMock()
    # Giả lập Gemini API ném lỗi (Ví dụ: Server Error / Quota exceeded)
    mock_instance.models.generate_content.side_effect = Exception("Gemini API internal error")
    mock_genai_client.return_value = mock_instance

    payload = {
        "question": "Phân tích lưu lượng giúp tôi",
        "parking_stats": {"total": 10}
    }
    
    response = client.post("/ai/ask", json=payload, headers=auth_headers)
    
    assert response.status_code == 500
    assert "lỗi" in response.json().get("detail", "").lower()


@patch("services.ai_service.genai.Client")
def test_ai_gemini_timeout(mock_genai_client, client: TestClient, auth_headers: dict):
    """5. Kiểm thử khi Gemini API bị timeout (Request timeout / Connection error)."""
    mock_instance = MagicMock()
    # Giả lập timeout exception
    mock_instance.models.generate_content.side_effect = TimeoutError("API Connection Timeout")
    mock_genai_client.return_value = mock_instance

    payload = {
        "question": "Thống kê tuần",
        "parking_stats": {"data": [1, 2, 3]}
    }
    
    response = client.post("/ai/ask", json=payload, headers=auth_headers)
    
    assert response.status_code == 500


@patch("services.ai_service.genai.Client")
def test_ai_anti_hallucination_constraint(mock_genai_client, client: TestClient, auth_headers: dict):
    """6. Kiểm thử quy tắc chống ảo giác (AI không được tự bịa đặt dữ liệu ngoài ngữ cảnh cung cấp)."""
    mock_instance = MagicMock()
    mock_response = MagicMock()
    # Theo System Prompt chống ảo giác, nếu không có thông tin, AI phải trả về câu từ chối chuẩn
    mock_response.text = "Tôi không có đủ dữ liệu để trả lời câu hỏi này."
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_client.return_value = mock_instance

    payload = {
        "question": "Xe có biển số 29B-999.99 vào lúc mấy giờ?",
        "parking_stats": {"active_sessions": [{"license_plate": "30A-111.11"}]}  # Không chứa biển số được hỏi
    }
    
    response = client.post("/ai/ask", json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    assert "không có đủ dữ liệu" in response.text


@patch("services.ai_service.genai.Client")
def test_ai_daily_report_success(mock_genai_client, client: TestClient, auth_headers: dict):
    """Kiểm thử bổ sung: POST /ai/daily-report tạo báo cáo ngày thành công với mock Gemini."""
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "1. Tóm tắt\nHoạt động ổn định.\n2. Đánh giá lưu lượng\nBình thường.\n3. Khung giờ cao điểm\n8h - 9h.\n4. Khuyến nghị\nGiữ nguyên nhân sự."
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_client.return_value = mock_instance

    payload = {
        "target_date": "2026-06-06",
        "parking_stats": {"total_vehicles": 50, "revenue": 1200000}
    }
    
    response = client.post("/ai/daily-report", json=payload, headers=auth_headers)
    
    assert response.status_code in [200, 201]
    assert "Tóm tắt" in response.text or "Hoạt động ổn định" in response.text


@patch("services.ai_service.genai.Client")
def test_ai_weekly_report_success(mock_genai_client, client: TestClient, auth_headers: dict):
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Lưu lượng tăng vào thứ Sáu; khung giờ cao điểm là 17:00."
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_client.return_value = mock_instance

    response = client.post(
        "/ai/weekly-report",
        headers=auth_headers,
        json={
            "start_date": "2026-08-03",
            "end_date": "2026-08-09",
            "weekly_data": [
                {"time_label": "2026-08-03", "total_vehicles": 20},
                {"time_label": "2026-08-08", "total_vehicles": 35},
            ],
        },
    )

    assert response.status_code == 200
    assert "thứ Sáu" in response.json()["content"]
    prompt = mock_instance.models.generate_content.call_args.kwargs["contents"]
    assert "2026-08-03" in prompt
    assert "total_vehicles" in prompt


@patch("services.ai_service.genai.Client")
def test_ai_staff_suggestion_success(mock_genai_client, client: TestClient, auth_headers: dict):
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Tăng cường nhân sự tại cổng vào trong khung 17:00."
    mock_instance.models.generate_content.return_value = mock_response
    mock_genai_client.return_value = mock_instance

    response = client.post(
        "/ai/staff-suggestion",
        headers=auth_headers,
        json={
            "hourly_traffic": [{"time_label": "17:00", "total_vehicles": 40}],
            "revenue": 1500000,
            "occupancy_rate": 82.5,
        },
    )

    assert response.status_code == 200
    assert "nhân sự" in response.json()["content"]
    prompt = mock_instance.models.generate_content.call_args.kwargs["contents"]
    assert "82.5" in prompt
    assert "1500000" in prompt


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/ai/daily-report", {"target_date": "2026-08-11", "parking_stats": {}}),
        (
            "/ai/weekly-report",
            {"start_date": "2026-08-05", "end_date": "2026-08-11", "weekly_data": []},
        ),
        (
            "/ai/staff-suggestion",
            {"hourly_traffic": [], "revenue": 0, "occupancy_rate": 0},
        ),
    ],
)
def test_ai_reports_reject_empty_data(client: TestClient, auth_headers: dict, path: str, payload: dict):
    response = client.post(path, headers=auth_headers, json=payload)
    assert response.status_code == 422


def test_ai_weekly_report_rejects_invalid_date_range(client: TestClient, auth_headers: dict):
    response = client.post(
        "/ai/weekly-report",
        headers=auth_headers,
        json={
            "start_date": "2026-08-11",
            "end_date": "2026-08-05",
            "weekly_data": [{"time_label": "2026-08-08", "total_vehicles": 10}],
        },
    )
    assert response.status_code == 422


def test_ai_dashboard_question_rejects_whitespace(client: TestClient, auth_headers: dict):
    response = client.post(
        "/ai/question",
        headers=auth_headers,
        json={"question": "   "},
    )
    assert response.status_code == 422
