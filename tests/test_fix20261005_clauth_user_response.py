"""CL-AUTH #10: stored accounts outside today's write rules never break reads.

UserResponse is a read model; validation applies to writes only. Public
registration strips text before validating it, so "  a" cannot be stored as a
one-character name.
"""

import pytest

from models.role import Role
from models.user import User
from services.auth_service import AuthService


def _headers(user):
    token = AuthService().create_access_token(user.id, user.username, user.role.name, password_hash=user.password_hash)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(db_session):
    role = Role(name="admin")
    db_session.add(role)
    db_session.flush()
    user = User(username="root_admin", full_name="Root Admin", role_id=role.id,
                password_hash=AuthService.get_password_hash("AdminPass1"), is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.mark.parametrize(("username", "full_name"), [
    ("admin@parking.vn", "admin@parking.vn"),
    ("ad", "Legacy short username"),
    ("legacy user", "Có dấu cách"),
    ("one_letter_name", "a"),
])
def test_non_conforming_stored_accounts_are_listed_and_readable(client, db_session, admin, username, full_name):
    legacy = User(username=username, full_name=full_name, role_id=admin.role_id,
                  password_hash=AuthService.get_password_hash("LegacyPass1"), is_active=True)
    db_session.add(legacy)
    db_session.commit()

    listed = client.get("/api/v1/users", headers=_headers(admin))
    assert listed.status_code == 200, listed.text
    assert {row["username"] for row in listed.json()} == {"root_admin", username}

    one = client.get(f"/api/v1/users/{legacy.id}", headers=_headers(admin))
    assert one.status_code == 200, one.text
    assert (one.json()["username"], one.json()["full_name"]) == (username, full_name)

    # The read model still never exposes credentials.
    assert "password_hash" not in one.json() and "password" not in one.json()


def test_admin_can_fix_a_non_conforming_account_after_reading_it(client, db_session, admin):
    legacy = User(username="admin@parking.vn", full_name="a", role_id=admin.role_id,
                  password_hash=AuthService.get_password_hash("LegacyPass1"), is_active=True)
    db_session.add(legacy)
    db_session.commit()
    fixed = client.put(f"/api/v1/users/{legacy.id}", headers=_headers(admin),
                       json={"username": "admin_parking", "full_name": "Quản trị bãi"})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["username"] == "admin_parking"


@pytest.mark.parametrize("full_name", [" a", "a ", "   "])
def test_registration_validates_the_stripped_name(client, full_name):
    response = client.post("/api/auth/register", json={
        "username": "cust_strip", "password": "Secret123!", "full_name": full_name, "role": "customer"})
    assert response.status_code == 422, response.text


def test_registration_strips_padded_username_and_name(client, db_session):
    response = client.post("/api/auth/register", json={
        "username": "  lan_khach ", "password": "Secret123!", "full_name": "  Lan Khách ", "role": "customer"})
    assert response.status_code == 201, response.text
    assert (response.json()["username"], response.json()["full_name"]) == ("lan_khach", "Lan Khách")
