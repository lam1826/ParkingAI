from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.audit import _classify_action, _extract_resource


def test_audit_classifies_scoped_operations():
    assert _classify_action("POST", "/api/v2/sites/1/check-in") == "CHECK_IN"
    assert _classify_action("PUT", "/api/v2/sites/1/sessions/abc/check-out") == "CHECK_OUT"
    assert _extract_resource("/api/v2/sites/1/cash-shifts/abc/close") == ("cash-shifts", "abc")


def test_request_id_is_returned_and_invalid_values_are_replaced():
    from middleware.request_context import RequestContextMiddleware
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    @app.get("/probe")
    def probe():
        return {"ok": True}
    client = TestClient(app)
    assert client.get("/probe", headers={"X-Request-ID": "probe-123"}).headers["X-Request-ID"] == "probe-123"
    response = client.get("/probe", headers={"X-Request-ID": "bad " * 100})
    assert 0 < len(response.headers["X-Request-ID"]) <= 64


def test_unhandled_errors_keep_correlation_without_leaking_details():
    from middleware.request_context import RequestContextMiddleware
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    @app.get("/broken")
    def broken():
        raise RuntimeError("private prompt and image contents")
    response = TestClient(app, raise_server_exceptions=False).get("/broken", headers={"X-Request-ID": "broken-123"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "broken-123"
    assert "private prompt" not in response.text
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
