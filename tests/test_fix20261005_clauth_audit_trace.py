"""CL-AUTH #64: an unhandled 500 on a mutation is in the audit log under its trace code.

The 500 body asks the user to quote its request_id; support must then be able
to find the failed mutation with GET /api/v1/audit-logs?request_id=...
Handled outcomes are still audited exactly once, and reads stay unaudited.
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from models.audit_log import AuditLog
from models.role import Role
from models.user import User
from services.auth_service import AuthService


def _headers(user, request_id=None):
    token = AuthService().create_access_token(user.id, user.username, user.role.name, password_hash=user.password_hash)
    headers = {"Authorization": f"Bearer {token}"}
    if request_id:
        headers["X-Request-ID"] = request_id
    return headers


@pytest.fixture
def admin(db_session):
    roles = {name: Role(name=name) for name in ("admin", "staff")}
    db_session.add_all(roles.values())
    db_session.flush()
    user = User(username="trace_admin", full_name="Trace Admin", role_id=roles["admin"].id,
                password_hash=AuthService.get_password_hash("AdminPass1"), is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def raw_client(client):
    """Same DB override as ``client`` but returns the 500 instead of raising it."""
    return TestClient(app, raise_server_exceptions=False)


def _boom(*args, **kwargs):
    raise RuntimeError("simulated code bug")


def _create_payload(db_session):
    staff = db_session.query(Role).filter_by(name="staff").one()
    return {"username": "trace_new_user", "full_name": "Trace User", "password": "TracePass1", "role_id": staff.id}


def test_unhandled_500_mutation_is_audited_and_findable_by_trace_code(raw_client, db_session, admin, monkeypatch):
    monkeypatch.setattr("crud.user.create_user", _boom)
    response = raw_client.post("/api/v1/users", json=_create_payload(db_session),
                               headers=_headers(admin, "trace-unhandled-500"))
    assert response.status_code == 500
    assert response.json()["request_id"] == "trace-unhandled-500"
    assert response.headers["x-request-id"] == "trace-unhandled-500"

    db_session.expire_all()
    rows = db_session.query(AuditLog).filter(AuditLog.request_id == "trace-unhandled-500").all()
    assert [(row.method, row.path, row.status_code, row.success, row.user_id, row.action) for row in rows] == [
        ("POST", "/api/v1/users", 500, False, admin.id, "CREATE")]

    lookup = raw_client.get("/api/v1/audit-logs", params={"request_id": "trace-unhandled-500"},
                            headers=_headers(admin))
    assert lookup.status_code == 200, lookup.text
    assert [(row["request_id"], row["status_code"], row["success"]) for row in lookup.json()] == [
        ("trace-unhandled-500", 500, False)]


def test_handled_outcomes_are_still_audited_once(client, db_session, admin):
    created = client.post("/api/v1/users", json=_create_payload(db_session),
                          headers=_headers(admin, "trace-created"))
    assert created.status_code == 201, created.text
    missing = client.put("/api/v1/users/999999", json={"full_name": "Nobody Here"},
                         headers=_headers(admin, "trace-missing"))
    assert missing.status_code == 404, missing.text

    db_session.expire_all()
    rows = {row.request_id: (row.status_code, row.success) for row in db_session.query(AuditLog).all()}
    assert rows == {"trace-created": (201, True), "trace-missing": (404, False)}


def test_unhandled_500_on_a_read_or_anonymous_call_adds_no_row(raw_client, db_session, admin, monkeypatch):
    monkeypatch.setattr("crud.user.get_users", _boom)
    monkeypatch.setattr("crud.user.create_user", _boom)
    read = raw_client.get("/api/v1/users", headers=_headers(admin, "trace-read-500"))
    assert read.status_code == 500
    anonymous = raw_client.post("/api/v1/users", json=_create_payload(db_session),
                                headers={"X-Request-ID": "trace-anonymous"})
    assert anonymous.status_code == 401

    db_session.expire_all()
    assert db_session.query(AuditLog).count() == 0
