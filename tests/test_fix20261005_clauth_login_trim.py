"""CL-AUTH #40: login normalizes the username the same way registration does.

Stored usernames never contain whitespace, so a leading/trailing space (phone
autocorrect) must not turn correct credentials into a failed, rate-limited login.
"""

import pytest
from sqlalchemy import select

from models.audit_log import AuditLog


@pytest.fixture
def customer(client):
    response = client.post("/api/auth/register", json={
        "username": "lan_khach", "password": "Secret123!", "full_name": "Lan Khach", "role": "customer"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("typed", ["lan_khach ", " lan_khach", "\tlan_khach\n"])
def test_json_login_accepts_surrounding_whitespace(client, db_session, customer, typed):
    response = client.post("/api/auth/login", json={"username": typed, "password": "Secret123!"})
    assert response.status_code == 200, response.text
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.json()["username"] == "lan_khach"
    failed = db_session.scalars(select(AuditLog).where(AuditLog.action == "LOGIN", AuditLog.success.is_(False))).all()
    assert failed == []


def test_oauth_form_login_accepts_surrounding_whitespace(client, customer):
    response = client.post("/auth/login", data={"username": "lan_khach ", "password": "Secret123!"})
    assert response.status_code == 200, response.text


def test_whitespace_only_and_wrong_password_still_fail(client, customer):
    blank = client.post("/api/auth/login", json={"username": "   ", "password": "Secret123!"})
    assert blank.status_code == 422
    wrong = client.post("/api/auth/login", json={"username": "lan_khach ", "password": "wrong-pass"})
    assert wrong.status_code == 401
    # Case stays significant: usernames are unique and matched case-sensitively.
    assert client.post("/api/auth/login", json={"username": "Lan_khach", "password": "Secret123!"}).status_code == 401
