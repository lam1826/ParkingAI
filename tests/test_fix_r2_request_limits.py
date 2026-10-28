"""Round 2 of the 28/10/2026 fix: request body limits through the whole application.

RequestLimitsMiddleware reads a body before routing, so it must be bounded in
size and in time, and must always answer: a request that is never completed
gets 408, a client that leaves mid-body gets 400 (never a 500 or an
unhandled-error log). JSON, forms and multipart share MAX_REQUEST_BODY_BYTES;
only the camera upload routes, which authenticate before reading and then read
at most a 2 MB image within 30 s themselves, are not buffered here (a declared
length above MAX_UPLOAD_BODY_BYTES is refused at once).
"""
import asyncio
import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from core.config import Settings, settings
from expansion import vision_router
from expansion.online_payment_router import get_payos_gateway
from main import app
from middleware import request_limits
from models.audit_log import AuditLog
from services.auth_service import AuthService

LIMIT, UPLOAD_LIMIT = settings.MAX_REQUEST_BODY_BYTES, settings.MAX_UPLOAD_BODY_BYTES
TOO_LARGE = "Dữ liệu gửi lên vượt giới hạn cho phép."


def _json_of_size(size):
    head, tail = b'{"username": "', b'", "password": "x"}'
    return head + b"u" * (size - len(head) - len(tail)) + tail


def _chunks(body, size=65_536):
    return iter([body[index:index + size] for index in range(0, len(body), size)])


def _staff_headers(user):
    token = AuthService().create_access_token(user.id, user.username, "staff", password_hash=user.password_hash)
    return [("authorization", f"Bearer {token}")]


def _scope(method, path, headers):
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
            "root_path": "", "headers": [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers],
            "client": ("203.0.113.77", 50000), "server": ("testserver", 80), "app": app}


def _drive(method, path, headers, receive, timeout=5):
    """Run the real application on one raw ASGI request; returns (status, body) or ('hung', b'')."""
    sent = []

    async def send(message):
        sent.append(message)

    async def run():
        try:
            await asyncio.wait_for(app(_scope(method, path, headers), receive, send), timeout)
        except asyncio.TimeoutError:
            return "hung", b""
        start = next(message for message in sent if message["type"] == "http.response.start")
        return start["status"], b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return asyncio.run(run())


def _first_then(first, after):
    calls = {"n": 0}

    async def receive():
        calls["n"] += 1
        if calls["n"] == 1:
            return {"type": "http.request", "body": first, "more_body": True}
        if after == "stall":
            await asyncio.Event().wait()
        return {"type": "http.disconnect"}
    return receive


def test_the_documented_defaults_are_1_mib_and_8_mib():
    defaults = Settings(_env_file=None, SECRET_KEY="limits-test-secret")
    assert (defaults.MAX_REQUEST_BODY_BYTES, defaults.MAX_UPLOAD_BODY_BYTES) == (1_048_576, 8_388_608)


def test_the_body_limit_is_exact_with_and_without_a_content_length(client):
    json_headers = {"Content-Type": "application/json"}
    at_limit, over = _json_of_size(LIMIT), _json_of_size(LIMIT + 1)
    # At the limit the body reaches validation (a username has at most 50 characters: 422).
    assert client.post("/api/auth/register", content=at_limit, headers=json_headers).status_code == 422
    refused = client.post("/api/auth/register", content=over, headers=json_headers)
    assert refused.status_code == 413 and refused.json() == {"detail": TOO_LARGE}
    # Chunked transfer, no Content-Length: the bytes that arrive are counted.
    assert client.post("/api/auth/register", content=_chunks(at_limit), headers=json_headers).status_code == 422
    assert client.post("/api/auth/register", content=_chunks(over), headers=json_headers).status_code == 413


def test_multipart_outside_the_camera_routes_gets_the_ordinary_limit(client):
    headers = {"Content-Type": "multipart/form-data; boundary=x"}
    body = b"--x\r\n" + b"a" * (LIMIT - 5)
    assert len(body) == LIMIT
    assert client.post("/api/auth/register", content=body, headers=headers).status_code != 413
    assert client.post("/api/auth/register", content=body + b"a", headers=headers).status_code == 413
    assert client.post("/auth/login", content=_chunks(body + b"a"), headers=headers).status_code == 413


def test_camera_uploads_authenticate_before_their_own_bounded_read(client, test_user):
    headers = {"Content-Type": "multipart/form-data; boundary=x"}
    # Not buffered before routing: an anonymous upload is refused by authentication, unread.
    anonymous = client.post("/api/v2/vision/observations", content=b"--x\r\n" + b"a" * (3 * 1024 * 1024), headers=headers)
    assert anonymous.status_code == 401, anonymous.text
    declared = client.post("/api/v2/vision/edge-events", content=b"a" * (UPLOAD_LIMIT + 1), headers=headers)
    assert declared.status_code == 413 and declared.json() == {"detail": TOO_LARGE}
    staff = {**headers, **dict(_staff_headers(test_user))}
    image = client.post("/api/v2/vision/observations", content=b"--x\r\n" + b"a" * (2 * 1024 * 1024 + 20_000), headers=staff)
    assert image.status_code == 413 and image.json()["detail"] == "Ảnh tải lên vượt giới hạn 2 MB."


def test_every_route_that_reads_an_upload_itself_is_exempt_from_buffering():
    readers = {route.path for route in vision_router.router.routes if isinstance(route, APIRoute)
               and route.endpoint in (vision_router.upload_observation, vision_router.edge_observation)}
    assert readers == request_limits.UPLOAD_PATHS
    # No other route accepts a file upload: every other multipart body keeps the ordinary limit.
    backend = Path(__file__).resolve().parents[1] / "backend"
    sources = [path for folder in ("routers", "expansion") for path in (backend / folder).glob("*.py")] + [backend / "main.py"]
    uploads = {path.name for path in sources
               if re.search(r"UploadFile|File\(|MultiPartParser", path.read_text(encoding="utf-8"))}
    assert uploads == {"vision_router.py"}


def test_a_stalled_camera_upload_still_gets_the_route_408(client, test_user, monkeypatch):
    real_timeout = asyncio.timeout
    monkeypatch.setattr(vision_router.asyncio, "timeout", lambda _seconds: real_timeout(0.05))
    headers = [*_staff_headers(test_user), ("content-type", "multipart/form-data; boundary=x")]
    status, body = _drive("POST", "/api/v2/vision/observations", headers, _first_then(b"--x\r\n", "stall"))
    assert status == 408 and json.loads(body)["detail"].startswith("Tải ảnh quá thời gian"), body
    # Without a token the request is answered before any body is read.
    status, _ = _drive("POST", "/api/v2/vision/observations", headers[1:], _first_then(b"--x\r\n", "stall"))
    assert status == 401


def test_a_stalled_body_gets_408_instead_of_holding_the_connection(client, monkeypatch):
    monkeypatch.setattr(request_limits, "BODY_TIMEOUT_SECONDS", 0.05)
    for content_type in ("application/json", "multipart/form-data; boundary=x"):
        status, body = _drive("POST", "/api/auth/register", [("content-type", content_type)], _first_then(b'{"user', "stall"))
        assert status == 408, (content_type, status)
        assert json.loads(body) == {"detail": request_limits.BODY_TIMEOUT}


def test_a_client_that_leaves_mid_body_gets_400_never_500(client, db_session, test_user, caplog):
    cases = (("/api/auth/login", [("content-type", "application/json")], b'{"username": "qa_staff", "pass',
              request_limits.BODY_INCOMPLETE),
             ("/api/v2/vision/observations", [*_staff_headers(test_user), ("content-type", "multipart/form-data; boundary=x")],
              b"--x\r\n", "Kết nối tải ảnh đã đóng."))
    for path, headers, first, detail in cases:
        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="parkingai.requests"):
            status, body = _drive("POST", path, headers, _first_then(first, "disconnect"))
        assert status == 400 and json.loads(body)["detail"] == detail, (path, status, body)
        assert not [record for record in caplog.records if "unhandled_request_error" in record.getMessage()], path
    db_session.expire_all()
    assert not [row for row in db_session.scalars(select(AuditLog)) if row.status_code >= 500]


def test_webhook_form_login_and_bodiless_delete_still_reach_their_routes(client, db_session, test_user):
    # payOS webhook: the route reads the replayed body itself (its own 64 KB bound and answers).
    app.dependency_overrides[get_payos_gateway] = lambda: None
    try:
        small = client.post("/api/v2/payments/payos/webhook", content=b'{"code": "00"}', headers={"Content-Type": "application/json"})
        assert small.status_code == 503 and small.json()["detail"] == "Kênh thanh toán chưa được cấu hình."
        large = client.post("/api/v2/payments/payos/webhook", content=b"x" * 65_537, headers={"Content-Type": "application/json"})
        assert large.status_code == 413 and large.json()["detail"] == "Thông báo thanh toán vượt giới hạn."
    finally:
        app.dependency_overrides.pop(get_payos_gateway, None)
    form = client.post("/auth/login", data={"username": "qa_staff", "password": "password123"})
    assert form.status_code == 200 and form.json()["token_type"] == "bearer", form.text
    from models.role import Role
    from models.user import User
    admin_role = Role(name="admin")
    db_session.add(admin_role)
    db_session.flush()
    admin = User(username="limits_admin", role_id=admin_role.id, full_name="Quản trị", is_active=True,
                 password_hash=AuthService.get_password_hash("Password123"))
    removable = User(username="limits_removable", role_id=admin_role.id, full_name="Tạm", is_active=True,
                     password_hash=AuthService.get_password_hash("Password123"))
    db_session.add_all([admin, removable])
    db_session.commit()
    token = AuthService().create_access_token(admin.id, admin.username, "admin", password_hash=admin.password_hash)
    deleted = client.delete(f"/api/v1/users/{removable.id}", headers={"Authorization": f"Bearer {token}"})
    assert deleted.status_code == 204, deleted.text


@pytest.fixture(autouse=True)
def _restore_overrides():
    yield
    app.dependency_overrides.pop(get_payos_gateway, None)
