"""Public auth accounting and last-admin regressions on isolated databases."""

from datetime import datetime, timedelta, timezone
import threading

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from core.config import settings
from database import Base, get_db
from main import app
from models.audit_log import AuditLog
from models.role import Role
from models.user import User
from routers import user as user_router
from services.auth_service import AuthService


@pytest.fixture(params=["malformed", "expired", "missing-sub", "deleted-user", "oversized-sub"])
def irrelevant_bearer(request):
    if request.param == "malformed":
        return "Bearer invalid-jwt"
    payload = {
        "sub": "999999",
        "username": "irrelevant-actor",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    if request.param == "expired":
        payload["exp"] = datetime.now(timezone.utc) - timedelta(minutes=5)
    elif request.param == "missing-sub":
        del payload["sub"]
    elif request.param == "oversized-sub":
        payload["sub"] = str(2**128)
    return "Bearer " + jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


@pytest.mark.parametrize("path", ["/api/auth/login", "/auth/login"])
def test_public_login_always_counts_attempts(client, db_session, monkeypatch, irrelevant_bearer, path):
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FAILURES", 2)
    credentials = {"username": "missing-user", "password": "wrong-password"}
    body = {"data" if path == "/auth/login" else "json": credentials}
    headers = {"Authorization": irrelevant_bearer}

    responses = [client.post(path, headers=headers, **body) for _ in range(3)]

    assert [response.status_code for response in responses] == [401, 401, 429]
    attempts = db_session.scalars(select(AuditLog).where(AuditLog.action == "LOGIN")).all()
    assert len(attempts) == 3
    assert all(row.user_id is None and row.username == "anonymous" for row in attempts)
    assert all(not row.success for row in attempts)


def test_public_registration_always_counts_attempts(client, db_session, monkeypatch, irrelevant_bearer):
    monkeypatch.setattr(settings, "AUTH_REGISTER_MAX_ATTEMPTS", 1)
    headers = {"Authorization": irrelevant_bearer}
    payload = {"username": "new_customer", "password": "password123", "full_name": "New Customer"}

    created = client.post("/api/auth/register", json=payload, headers=headers)
    blocked = client.post("/api/auth/register", json={**payload, "username": "second_customer"}, headers=headers)

    assert [created.status_code, blocked.status_code] == [201, 429]
    attempts = db_session.scalars(select(AuditLog).where(AuditLog.action == "REGISTER")).all()
    assert len(attempts) == 2
    assert all(row.user_id is None and row.username == "anonymous" for row in attempts)
    assert db_session.scalar(select(func.count(User.id))) == 1


@pytest.fixture
def admin_race_client(tmp_path):
    # File-backed SQLite and separate request sessions exercise real database
    # locking, unlike the shared in-memory Session used by ordinary API tests.
    engine = create_engine(
        "sqlite:///" + (tmp_path / "admin-race.db").as_posix(),
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def scratch_db():
        with factory() as db:
            yield db

    with factory() as db:
        admin = Role(name="admin")
        manager = Role(name="manager")
        db.add_all([admin, manager])
        db.flush()
        users = [User(username=f"admin_{i}", full_name=f"Admin {i}", password_hash="unused", role_id=admin.id, is_active=True) for i in range(2)]
        db.add_all(users)
        db.commit()
        first_id, second_id, manager_id = users[0].id, users[1].id, manager.id

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = scratch_db
    try:
        with TestClient(app) as client:
            yield client, factory, first_id, second_id, manager_id
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _headers(user_id):
    token = AuthService().create_access_token(user_id, f"admin_{user_id}", "admin")
    return {"Authorization": "Bearer " + token}


def _active_admins(factory):
    with factory() as db:
        return db.scalar(select(func.count(User.id)).join(Role).where(Role.name == "admin", User.is_active.is_(True)))


def test_inflight_delete_cannot_remove_admin_left_by_self_demotion(admin_race_client, monkeypatch):
    client, factory, first_id, second_id, manager_id = admin_race_client
    paused = threading.Event()
    proceed = threading.Event()
    original_get = user_router.crud_user.get_user
    outcome, errors = [], []

    def pause_delete(db, user_id):
        found = original_get(db, user_id)
        if user_id == second_id:
            paused.set()
            assert proceed.wait(10), "Delete synchronization timed out"
        return found

    def delete_other_admin():
        try:
            outcome.append(client.delete(f"/api/v1/users/{second_id}", headers=_headers(first_id)))
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(user_router.crud_user, "get_user", pause_delete)
    worker = threading.Thread(target=delete_other_admin)
    worker.start()
    try:
        assert paused.wait(10), "Delete did not reach synchronization point"
        demotion = client.put(f"/api/v1/users/{first_id}", headers=_headers(first_id), json={"role_id": manager_id})
    finally:
        proceed.set()
        worker.join(10)

    assert not worker.is_alive()
    assert not errors, errors
    assert demotion.status_code == 200, demotion.text
    assert outcome[0].status_code == 409, outcome[0].text
    assert _active_admins(factory) == 1


@pytest.mark.parametrize("change", ["demote", "deactivate"])
def test_admin_guard_holds_until_commit_and_rechecks_waiting_update(admin_race_client, monkeypatch, change):
    client, factory, first_id, second_id, manager_id = admin_race_client
    first_guard_passed = threading.Event()
    second_guard_entered = threading.Event()
    second_guard_finished = threading.Event()
    allow_first_commit = threading.Event()
    original_update = user_router.crud_user.update_user
    original_guard = user_router._ensure_active_admin_remains
    responses, errors = {}, []

    def hold_first_commit(db, db_user, user_in):
        if db_user.id == first_id:
            first_guard_passed.set()
            assert allow_first_commit.wait(10), "First commit synchronization timed out"
        return original_update(db, db_user, user_in)

    def observe_guard(db, db_user, user_in):
        if db_user.id == second_id:
            second_guard_entered.set()
        try:
            return original_guard(db, db_user, user_in)
        finally:
            if db_user.id == second_id:
                second_guard_finished.set()

    def update_admin(user_id):
        try:
            payload = {"role_id": manager_id} if change == "demote" else {"is_active": False}
            responses[user_id] = client.put(f"/api/v1/users/{user_id}", headers=_headers(user_id), json=payload)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(user_router.crud_user, "update_user", hold_first_commit)
    monkeypatch.setattr(user_router, "_ensure_active_admin_remains", observe_guard)
    first = threading.Thread(target=update_admin, args=(first_id,))
    second = threading.Thread(target=update_admin, args=(second_id,))
    first.start()
    try:
        assert first_guard_passed.wait(10)
        second.start()
        assert second_guard_entered.wait(10)
        # Before the fix both guards could pass while the first admin's
        # removal was still uncommitted. The second must wait for that commit.
        assert not second_guard_finished.wait(1), "Admin guard did not hold a transaction lock"
    finally:
        allow_first_commit.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)

    assert not first.is_alive() and not second.is_alive()
    assert not errors, errors
    assert sorted(response.status_code for response in responses.values()) == [200, 409]
    assert _active_admins(factory) == 1
