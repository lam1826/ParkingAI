from fastapi.testclient import TestClient


def test_api_responses_include_production_security_headers(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )


def test_auth_and_api_responses_are_never_cacheable(
    client: TestClient,
) -> None:
    login = client.post(
        "/api/auth/login",
        json={"username": "missing", "password": "wrong-password"},
    )
    protected = client.get("/api/v1/zones")

    assert login.headers["cache-control"] == "no-store"
    assert protected.headers["cache-control"] == "no-store"
