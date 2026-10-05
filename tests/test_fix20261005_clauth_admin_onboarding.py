"""CL-AUTH #3: Admin onboarding of staff/manager accounts reaches a usable lot.

Admin-created staff and managers must get the same site membership a
Manager-created staff gets when the install has exactly one active lot, and an
Admin must be able to choose the lot explicitly in a multi-lot install.
"""

import pytest
from sqlalchemy import select

from expansion.site_models import ParkingSite, SiteMembership
from models.role import Role
from models.user import User
from services.auth_service import AuthService


def _headers(user):
    token = AuthService().create_access_token(user.id, user.username, user.role.name, password_hash=user.password_hash)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def onboarding(db_session):
    roles = {name: Role(name=name) for name in ("admin", "manager", "staff", "customer")}
    db_session.add_all(roles.values())
    db_session.flush()
    admin = User(username="root_admin", full_name="Root Admin", role_id=roles["admin"].id,
                 password_hash=AuthService.get_password_hash("AdminPass1"), is_active=True)
    site = ParkingSite(name="Only active lot")
    db_session.add_all([admin, site])
    db_session.commit()
    return {"roles": roles, "admin": admin, "site": site}


def _payload(onboarding, username, role="staff", **extra):
    return {"username": username, "full_name": f"Account {username}", "password": "StaffPass1",
            "role_id": onboarding["roles"][role].id, "is_active": True, **extra}


def _memberships(db_session, user_id):
    return [(row.site_id, row.role) for row in db_session.scalars(
        select(SiteMembership).where(SiteMembership.user_id == user_id))]


@pytest.mark.parametrize("role", ["staff", "manager"])
def test_admin_created_operator_gets_the_only_active_lot(client, db_session, onboarding, role):
    response = client.post("/api/v1/users", headers=_headers(onboarding["admin"]),
                           json=_payload(onboarding, f"admin_made_{role}", role))
    assert response.status_code == 201, response.text
    created = response.json()
    assert _memberships(db_session, created["id"]) == [(onboarding["site"].id, role)]

    login = client.post("/api/auth/login", json={"username": created["username"], "password": "StaffPass1"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    caps = client.get("/api/v2/system/capabilities", headers=headers).json()
    assert caps["legacy_workspace_allowed"] is True
    assert [row["id"] for row in client.get("/api/v2/sites", headers=headers).json()] == [onboarding["site"].id]
    assert client.get(f"/api/v2/sites/{onboarding['site'].id}/availability", headers=headers).status_code == 200


def test_inactive_lots_do_not_block_single_active_lot_assignment(client, db_session, onboarding):
    db_session.add(ParkingSite(name="Closed historical lot", is_active=False))
    db_session.commit()
    response = client.post("/api/v1/users", headers=_headers(onboarding["admin"]),
                           json=_payload(onboarding, "staff_with_history_lot"))
    assert response.status_code == 201, response.text
    assert _memberships(db_session, response.json()["id"]) == [(onboarding["site"].id, "staff")]


def test_admin_picks_the_lot_in_a_multi_lot_install(client, db_session, onboarding):
    second = ParkingSite(name="Second active lot")
    db_session.add(second)
    db_session.commit()
    headers = _headers(onboarding["admin"])

    unassigned = client.post("/api/v1/users", headers=headers, json=_payload(onboarding, "pending_staff"))
    assert unassigned.status_code == 201, unassigned.text
    assert _memberships(db_session, unassigned.json()["id"]) == []

    chosen = client.post("/api/v1/users", headers=headers,
                         json=_payload(onboarding, "second_lot_manager", "manager", site_id=second.id))
    assert chosen.status_code == 201, chosen.text
    assert _memberships(db_session, chosen.json()["id"]) == [(second.id, "manager")]


@pytest.mark.parametrize("case", ["customer_role", "missing_site", "inactive_site"])
def test_invalid_site_choice_is_rejected_without_creating_the_account(client, db_session, onboarding, case):
    closed = ParkingSite(name="Closed lot", is_active=False)
    db_session.add(closed)
    db_session.commit()
    role, site_id = {"customer_role": ("customer", onboarding["site"].id),
                     "missing_site": ("staff", 999_999),
                     "inactive_site": ("staff", closed.id)}[case]
    before = db_session.query(User).count()
    response = client.post("/api/v1/users", headers=_headers(onboarding["admin"]),
                           json=_payload(onboarding, f"bad_{case}", role, site_id=site_id))
    assert response.status_code in {404, 422}, response.text
    assert db_session.query(User).count() == before


def test_admin_customer_and_admin_accounts_get_no_lot(client, db_session, onboarding):
    headers = _headers(onboarding["admin"])
    for role in ("customer", "admin"):
        response = client.post("/api/v1/users", headers=headers, json=_payload(onboarding, f"plain_{role}", role))
        assert response.status_code == 201, response.text
        assert _memberships(db_session, response.json()["id"]) == []


def test_manager_cannot_redirect_staff_to_another_lot(client, db_session, onboarding):
    manager = User(username="lot_manager", full_name="Lot Manager", role_id=onboarding["roles"]["manager"].id,
                   password_hash="unused", is_active=True)
    db_session.add(manager)
    db_session.flush()
    db_session.add(SiteMembership(site_id=onboarding["site"].id, user_id=manager.id, role="manager"))
    db_session.commit()
    headers = _headers(manager)
    elsewhere = client.post("/api/v1/users", headers=headers,
                            json=_payload(onboarding, "redirected_staff", site_id=onboarding["site"].id + 1000))
    assert elsewhere.status_code == 403, elsewhere.text
    same = client.post("/api/v1/users", headers=headers,
                       json=_payload(onboarding, "own_lot_staff", site_id=onboarding["site"].id))
    assert same.status_code == 201, same.text
    assert _memberships(db_session, same.json()["id"]) == [(onboarding["site"].id, "staff")]


def test_admin_can_still_delete_an_assigned_account_without_history(client, db_session, onboarding):
    headers = _headers(onboarding["admin"])
    created = client.post("/api/v1/users", headers=headers, json=_payload(onboarding, "short_lived_staff"))
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert client.delete(f"/api/v1/users/{user_id}", headers=headers).status_code == 204
    assert db_session.get(User, user_id) is None
    assert _memberships(db_session, user_id) == []
