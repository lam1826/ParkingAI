"""Fix 28/10/2026, round 2, on real PostgreSQL: the HTTP boundary and account rules.

G3: an offset, page or limit past bigint is PostgreSQL's numeric_value_out_of_range
(sqlstate 22003), answered 422 and logged as a warning, never 500; an id past
bigint compares as numeric and is simply not found. BD-2: catalog names are
checked and written under one advisory lock. BS-5: an admin deactivation stamps
the password hash it read under the row lock, so a password the user changed
at the same moment is never lost. Requests go through the real application
(FastAPI TestClient, real JWT auth) against a disposable alembic-head database.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, local

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from database import get_db
from expansion.site_models import ParkingSite
from main import app
from models import Role, User
from schemas.auth import ChangePasswordRequest
from schemas.user import UserUpdate
from services.auth_service import AuthService
from test_postgres_integration import _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="Requires an isolated local PostgreSQL service")

BIG = 2**63


@contextmanager
def _pg_client(engine):
    def override_get_db():
        db = Session(engine)
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _admin(engine):
    """A global admin: the migrated database already holds the default lot, so the legacy
    /api/v1 lists are open to admins only."""
    with Session(engine) as db:
        role, site = Role(name="admin"), ParkingSite(name="Bãi PostgreSQL")
        db.add_all([role, site])
        db.flush()
        user = User(username="pg-range-admin", role_id=role.id, full_name="Quản trị", is_active=True,
                    password_hash=AuthService.get_password_hash("Password123"))
        db.add(user)
        db.commit()
        token = AuthService().create_access_token(user.id, user.username, "admin", password_hash=user.password_hash)
        return site.id, {"Authorization": f"Bearer {token}"}


def test_numbers_past_bigint_are_422_on_postgresql_and_logged(caplog):
    with _isolated_checkout_postgres() as engine, _pg_client(engine) as client:
        site_id, headers = _admin(engine)
        with caplog.at_level(logging.WARNING, logger="main"):
            for path in (f"/api/v1/customers?skip={BIG}", f"/api/v1/monthly-passes?skip={BIG}",
                         f"/api/v2/sites/{site_id}/sessions?offset={BIG}", f"/api/v2/sites/{site_id}/payments?page={BIG - 1}",
                         f"/api/v2/sites/{site_id}/refund-requests?offset={BIG}"):
                response = client.get(path, headers=headers)
                assert response.status_code == 422, (path, response.status_code, response.text)
                assert response.json() == {"detail": "Giá trị số vượt giới hạn cho phép."}, path
        warnings = [record.getMessage() for record in caplog.records if record.name == "main" and record.levelno == logging.WARNING]
        assert len(warnings) == 5 and all("sqlstate 22003" in message for message in warnings), warnings
        assert not any(str(BIG) in message for message in warnings)
        # An id past bigint is refused or simply not found (PostgreSQL compares it as numeric), never a 500.
        for path in (f"/api/v1/customers/{BIG}", f"/api/v1/vehicles/{BIG}", f"/api/v2/sites/{BIG}/sessions"):
            assert client.get(path, headers=headers).status_code in (404, 422), path


def test_catalog_names_are_checked_under_the_advisory_lock_on_postgresql():
    with _isolated_checkout_postgres() as engine, _pg_client(engine) as client:
        site_id, headers = _admin(engine)
        created = client.post("/api/v1/vehicle-types", json={"name": "Xe máy", "requires_plate": True}, headers=headers)
        assert created.status_code == 201, created.text
        twin = client.post("/api/v1/vehicle-types", json={"name": "xe  MAY", "requires_plate": True}, headers=headers)
        assert twin.status_code == 409 and twin.json()["detail"] == "Tên loại xe đã tồn tại."
        zone = client.post(f"/api/v2/sites/{site_id}/zones", json={"name": "Khu Đông", "capacity": 5}, headers=headers)
        assert zone.status_code == 201, zone.text
        assert client.post(f"/api/v2/sites/{site_id}/zones", json={"name": "khu dong", "capacity": 5}, headers=headers).status_code == 409
        renamed = client.patch(f"/api/v2/sites/{site_id}/zones/{zone.json()['id']}", json={"name": "Khu Tây"}, headers=headers)
        assert renamed.status_code == 200 and renamed.json()["name"] == "Khu Tây", renamed.text


def test_a_deactivation_never_overwrites_a_password_changed_at_the_same_moment():
    from routers.auth import change_password
    from routers.user import update_user
    with _isolated_checkout_postgres() as engine:
        with Session(engine) as db:
            roles = {name: Role(name=name) for name in ("admin", "staff")}
            db.add_all(roles.values())
            db.flush()
            admin = User(username="pg-stamp-admin", role_id=roles["admin"].id, full_name="Quản trị", is_active=True,
                         password_hash=AuthService.get_password_hash("AdminPass1"))
            target = User(username="pg-stamp-target", role_id=roles["staff"].id, full_name="Nhân viên", is_active=True,
                          password_hash=AuthService.get_password_hash("OldPass123"))
            db.add_all([admin, target])
            db.commit()
            ids = dict(admin=admin.id, target=target.id)

        paused, changed_first, worker = Event(), Event(), local()

        def hold_before_update(connection, cursor, statement, parameters, context, many):
            # The deactivation has read the hash it will stamp; the user changes the password now,
            # and the deactivation waits until that change finishes (or cannot finish: 3 s).
            if getattr(worker, "admin", False) and statement.lstrip().upper().startswith("UPDATE USERS SET"):
                paused.set()
                changed_first.wait(3)

        def deactivate():
            worker.admin = True
            with Session(engine) as db:
                return update_user(ids["target"], UserUpdate(is_active=False), db, db.get(User, ids["admin"])).is_active

        def change():
            assert paused.wait(10), "the deactivation never reached its update"
            with Session(engine) as db:
                try:
                    change_password(ChangePasswordRequest(current_password="OldPass123", new_password="NewPass456"),
                                    db.get(User, ids["target"]), db)
                    return 200
                except Exception as exc:  # noqa: BLE001 - the HTTP status the route answers
                    db.rollback()
                    return getattr(exc, "status_code", 500)
                finally:
                    changed_first.set()

        event.listen(engine, "before_cursor_execute", hold_before_update)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                deactivated, changed = pool.submit(deactivate), pool.submit(change)
                results = deactivated.result(timeout=30), changed.result(timeout=30)
        finally:
            event.remove(engine, "before_cursor_execute", hold_before_update)
        with Session(engine) as db:
            stored = db.get(User, ids["target"])
            verify = AuthService().verify_password
            assert stored.is_active is False and results[0] is False
            # Either the change waited for the deactivation and was refused (409), or it won and
            # the stamped hash is the new one: a reported success is never silently undone.
            if results[1] == 200:
                assert verify("NewPass456", stored.password_hash), "the changed password was lost"
            else:
                assert results[1] == 409 and verify("OldPass123", stored.password_hash)
