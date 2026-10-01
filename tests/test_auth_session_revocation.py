"""Password changes revoke bearer sessions at the real HTTP auth boundary."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from core.config import settings
from database import Base, get_db
from main import app
from models.role import Role
from models.user import User
from services.auth_service import AuthService


def login(client, username, password="password123", *, oauth=False):
    credentials = {"username": username, "password": password}
    response = client.post("/auth/login" if oauth else "/api/auth/login",
                           **{"data" if oauth else "json": credentials})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.mark.parametrize("oauth", [False, True])
def test_password_change_revokes_all_existing_sessions_and_new_login_works(client, test_user, oauth):
    username = test_user.username
    first = login(client, username, oauth=oauth)
    second = login(client, username, oauth=not oauth)
    for headers in (first, second):
        assert client.get("/api/auth/me", headers=headers).status_code == 200

    changed = client.put("/api/auth/me/password", headers=first,
                         json={"current_password": "password123", "new_password": "changed-password-123"})
    assert changed.status_code == 200, changed.text
    for headers in (first, second):
        denied = client.get("/api/auth/me", headers=headers)
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"] == "Bearer"
    assert client.post("/api/auth/login", json={"username": username, "password": "password123"}).status_code == 401
    fresh = login(client, username, "changed-password-123", oauth=oauth)
    assert client.get("/api/auth/me", headers=fresh).status_code == 200

    # A second change immediately afterwards cannot reuse a timestamp window.
    assert client.put("/api/auth/me/password", headers=fresh,
                      json={"current_password": "changed-password-123", "new_password": "changed-again-123"}).status_code == 200
    assert client.get("/api/auth/me", headers=fresh).status_code == 401
    assert client.get("/api/auth/me", headers=login(client, username, "changed-again-123")).status_code == 200


@pytest.mark.parametrize("reset_password", ["admin-reset-123", "password123"])
def test_admin_reset_revokes_target_sessions_even_when_password_is_reused(client, db_session, test_user, reset_password):
    role = Role(name="admin")
    db_session.add(role)
    db_session.flush()
    admin = User(username="session_admin", full_name="Session Admin", role_id=role.id,
                 password_hash=AuthService.get_password_hash("admin-password-123"), is_active=True)
    db_session.add(admin)
    db_session.commit()
    admin_headers = login(client, admin.username, "admin-password-123")
    target_headers = login(client, test_user.username)
    response = client.put(f"/api/v1/users/{test_user.id}", headers=admin_headers,
                          json={"password": reset_password})
    assert response.status_code == 200, response.text
    assert "password_hash" not in response.json()
    assert client.get("/api/auth/me", headers=target_headers).status_code == 401
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200
    assert client.get("/api/auth/me", headers=login(client, test_user.username, reset_password)).status_code == 200


@pytest.mark.parametrize("current,new", [("wrong-current", "new-password-123"), ("password123", "password123")])
def test_rejected_change_does_not_revoke_session(client, test_user, current, new):
    headers = login(client, test_user.username)
    response = client.put("/api/auth/me/password", headers=headers,
                          json={"current_password": current, "new_password": new})
    assert response.status_code == 400
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_profile_edit_keeps_session_and_inactive_account_cannot_use_it(client, db_session, test_user):
    headers = login(client, test_user.username)
    assert client.put("/api/auth/me", headers=headers,
                      json={"username": "renamed_session_user", "full_name": "Renamed User"}).status_code == 200
    profile = client.get("/api/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["username"] == "renamed_session_user"
    test_user.is_active = False
    db_session.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/login", json={"username": test_user.username, "password": "password123"}).status_code == 400


@pytest.mark.parametrize("claim", [None, "", "forged-binding", 123, [], {}, "ký-tự"])
def test_signed_legacy_or_invalid_credential_binding_is_rejected(client, test_user, claim):
    # Tests the JWT verification boundary, not whether an attacker has the key.
    payload = {"sub": str(test_user.id), "username": test_user.username, "role": "staff",
               "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
    if claim is not None:
        payload["credential_version"] = claim
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_login_token_does_not_expose_password_or_stored_hash(client, test_user):
    headers = login(client, test_user.username)
    payload = jwt.decode(headers["Authorization"].split(" ", 1)[1], settings.SECRET_KEY,
                         algorithms=[settings.ALGORITHM])
    assert isinstance(payload.get("credential_version"), str)
    assert "password_hash" not in payload and "password" not in payload
    assert test_user.password_hash not in str(payload)
    assert "password123" not in str(payload)


@pytest.mark.parametrize("subject", [None, [], {}, "abc", "0", "-1", str(2**128)])
def test_invalid_subject_is_rejected_without_database_error(client, test_user, subject):
    headers = login(client, test_user.username)
    payload = jwt.decode(headers["Authorization"].split(" ", 1)[1], settings.SECRET_KEY,
                         algorithms=[settings.ALGORITHM])
    payload["sub"] = subject
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


@pytest.fixture
def isolated_auth_client(tmp_path):
    """Each HTTP request/reset has its own Session and real SQLite connection."""
    engine = create_engine("sqlite:///" + (tmp_path / "auth-race.db").as_posix(),
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        role = Role(name="staff")
        db.add(role)
        db.flush()
        user = User(username="race_user", full_name="Race User", role_id=role.id,
                    password_hash=AuthService.get_password_hash("password123"), is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id

    def request_db():
        with factory() as db:
            yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = request_db
    try:
        with TestClient(app) as client:
            yield client, factory, user_id
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def test_inflight_password_change_cannot_overwrite_a_newer_reset(isolated_auth_client, monkeypatch):
    client, factory, user_id = isolated_auth_client
    headers = login(client, "race_user")
    original_hash = AuthService.get_password_hash
    reset_hash = original_hash("newer-admin-reset-123")

    def reset_before_write(password):
        # Commit through another connection after current-password validation.
        with factory() as db:
            db.execute(update(User).where(User.id == user_id).values(password_hash=reset_hash))
            db.commit()
        return original_hash(password)

    monkeypatch.setattr(AuthService, "get_password_hash", staticmethod(reset_before_write))
    response = client.put("/api/auth/me/password", headers=headers,
                          json={"current_password": "password123", "new_password": "stale-user-change-123"})
    assert response.status_code == 409, response.text
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/auth/me", headers=login(client, "race_user", "newer-admin-reset-123")).status_code == 200


def test_login_racing_with_reset_cannot_issue_a_current_session_from_old_password(isolated_auth_client, monkeypatch):
    client, factory, user_id = isolated_auth_client
    authenticate = AuthService.authenticate_user
    reset_hash = AuthService.get_password_hash("newer-admin-reset-123")

    def reset_after_authentication(self, db, username, password):
        user = authenticate(self, db, username, password)
        with factory() as reset_db:
            reset_db.execute(update(User).where(User.id == user_id).values(password_hash=reset_hash))
            reset_db.commit()
        return user

    monkeypatch.setattr(AuthService, "authenticate_user", reset_after_authentication)
    stale = login(client, "race_user")
    assert client.get("/api/auth/me", headers=stale).status_code == 401
    monkeypatch.setattr(AuthService, "authenticate_user", authenticate)
    assert client.get("/api/auth/me", headers=login(client, "race_user", "newer-admin-reset-123")).status_code == 200
