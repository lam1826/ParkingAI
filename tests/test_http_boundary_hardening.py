from starlette.requests import Request

from core.client_ip import get_client_ip
from core.config import settings


def _request_with_fly_header():
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"fly-client-ip", b"203.0.113.77")],
        "client": ("198.51.100.9", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "root_path": "",
        "http_version": "1.1",
    })


def test_fly_client_ip_is_used_only_for_a_trusted_edge(monkeypatch):
    request = _request_with_fly_header()
    monkeypatch.setattr(settings, "TRUSTED_EDGE_PROXY", False)
    assert get_client_ip(request) == "198.51.100.9"
    monkeypatch.setattr(settings, "TRUSTED_EDGE_PROXY", True)
    assert get_client_ip(request) == "203.0.113.77"


def test_validation_errors_never_echo_password_or_registration_secrets(client):
    password = "secret7"
    registration_code = "private-code-" * 30
    response = client.post("/api/auth/register", json={
        "username": "safe-user",
        "full_name": "Safe User",
        "password": password,
        "role": "manager",
        "registration_code": registration_code,
    })
    assert response.status_code == 422
    assert password not in response.text
    assert registration_code not in response.text
    for error in response.json()["detail"]:
        if any("password" in str(part) or "registration_code" in str(part) for part in error["loc"]):
            assert "input" not in error
