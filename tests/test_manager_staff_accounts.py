"""A lot manager manages staff accounts without gaining admin authority."""

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.exc import IntegrityError

from expansion.site_models import ParkingSite, SiteMembership
from models.role import Role
from models.user import User
from services.auth_service import AuthService
from routers import user as user_router


def _headers(user):
    return {"Authorization": "Bearer " + AuthService().create_access_token(user.id, user.username, user.role.name)}


@pytest.fixture
def accounts(db_session, manager_user):
    site = ParkingSite(name="Staff account lot")
    db_session.add(site)
    db_session.flush()
    db_session.add(SiteMembership(site_id=site.id, user_id=manager_user.id, role="manager"))
    roles = {role.name: role for role in db_session.scalars(select(Role)).all()}
    for name in ("admin", "customer"):
        roles[name] = Role(name=name)
        db_session.add(roles[name])
    db_session.flush()
    actors = {"manager": manager_user}
    for name, role_name, membership in (
        ("staff", "staff", "staff"), ("unassigned", "staff", None),
        ("site_manager", "staff", "manager"), ("peer", "manager", "manager"),
        ("admin", "admin", None), ("customer", "customer", None),
    ):
        actor = User(username=f"account_{name}", full_name=f"Account {name}",
                     role_id=roles[role_name].id, password_hash="unused", is_active=True)
        db_session.add(actor)
        db_session.flush()
        if membership:
            db_session.add(SiteMembership(site_id=site.id, user_id=actor.id, role=membership))
        actors[name] = actor
    db_session.commit()
    return {"site": site, "roles": roles, **actors}


def _create_payload(accounts, **changes):
    return {"username": "new_staff_account", "full_name": "New staff", "password": "password123",
            "role_id": accounts["roles"]["staff"].id, "is_active": True, **changes}


def test_manager_creates_staff_with_membership_and_working_login(client, db_session, accounts):
    response = client.post("/api/v1/users", headers=_headers(accounts["manager"]), json=_create_payload(accounts))
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["role"]["name"] == "staff"
    assert "password_hash" not in created and "password" not in created
    membership = db_session.scalar(select(SiteMembership).where(SiteMembership.user_id == created["id"]))
    assert (membership.site_id, membership.role) == (accounts["site"].id, "staff")
    login = client.post("/api/auth/login", json={"username": created["username"], "password": "password123"})
    assert login.status_code == 200, login.text
    capabilities = client.get("/api/v2/system/capabilities", headers={"Authorization": "Bearer " + login.json()["access_token"]})
    assert capabilities.status_code == 200
    assert capabilities.json()["legacy_workspace_allowed"] is True


def test_manager_lock_blocks_existing_staff_token_and_preserves_membership(client, db_session, accounts):
    staff_headers = _headers(accounts["staff"])
    assert client.get("/api/auth/me", headers=staff_headers).status_code == 200
    url = f"/api/v1/users/{accounts['staff'].id}"
    response = client.put(url, headers=_headers(accounts["manager"]), json={"is_active": False})
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    assert client.get("/api/auth/me", headers=staff_headers).status_code == 401
    assert db_session.scalar(select(SiteMembership).where(SiteMembership.user_id == accounts["staff"].id)) is not None
    assert client.put(url, headers=_headers(accounts["manager"]), json={"is_active": True}).status_code == 200


def test_manager_can_edit_staff_profile_and_reset_password(client, accounts):
    response = client.put(f"/api/v1/users/{accounts['staff'].id}", headers=_headers(accounts["manager"]),
                          json={"full_name": "Updated staff", "username": "updated_staff",
                                "password": "changed-password", "role_id": accounts["staff"].role_id})
    assert response.status_code == 200, response.text
    login = client.post("/api/auth/login", json={"username": "updated_staff", "password": "changed-password"})
    assert login.status_code == 200


@pytest.mark.parametrize("role_name", ("admin", "manager", "customer"))
def test_manager_cannot_create_nonstaff_accounts(client, db_session, accounts, role_name):
    before = db_session.query(User).count()
    response = client.post("/api/v1/users", headers=_headers(accounts["manager"]),
                           json=_create_payload(accounts, role_id=accounts["roles"][role_name].id))
    assert response.status_code == 403
    assert db_session.query(User).count() == before


@pytest.mark.parametrize("target", ("manager", "peer", "admin", "customer", "unassigned", "site_manager"))
def test_manager_cannot_modify_other_privileged_or_unassigned_accounts(client, db_session, accounts, target):
    user = accounts[target]
    response = client.put(f"/api/v1/users/{user.id}", headers=_headers(accounts["manager"]), json={"is_active": False})
    assert response.status_code == 403
    db_session.refresh(user)
    assert user.is_active is True


@pytest.mark.parametrize("role_name", ("manager", "admin", "customer"))
def test_manager_cannot_change_staff_role(client, db_session, accounts, role_name):
    response = client.put(f"/api/v1/users/{accounts['staff'].id}", headers=_headers(accounts["manager"]),
                          json={"role_id": accounts["roles"][role_name].id})
    assert response.status_code == 403
    db_session.refresh(accounts["staff"])
    assert accounts["staff"].role.name == "staff"


def test_manager_lists_only_own_account_and_managed_staff(client, accounts):
    headers = _headers(accounts["manager"])
    listed = client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 200
    assert {user["id"] for user in listed.json()} == {accounts["manager"].id, accounts["staff"].id}
    assert client.get(f"/api/v1/users/{accounts['staff'].id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/users/{accounts['admin'].id}", headers=headers).status_code == 403
    assert client.get(f"/api/v1/users/{accounts['unassigned'].id}", headers=headers).status_code == 403


def test_staff_cannot_create_accounts_and_manager_cannot_delete(client, db_session, accounts):
    assert client.post("/api/v1/users", headers=_headers(accounts["staff"]), json=_create_payload(accounts)).status_code == 403
    assert client.delete(f"/api/v1/users/{accounts['staff'].id}", headers=_headers(accounts["manager"])).status_code == 403
    assert db_session.get(User, accounts["staff"].id) is not None


@pytest.mark.parametrize("boundary", ("no_site", "closed_site", "two_sites", "no_membership", "demoted_membership"))
def test_manager_cannot_create_outside_single_managed_lot(client, db_session, accounts, boundary):
    member = db_session.scalar(select(SiteMembership).where(SiteMembership.user_id == accounts["manager"].id))
    if boundary == "no_site":
        db_session.query(SiteMembership).delete()
        db_session.delete(accounts["site"])
    elif boundary == "closed_site":
        accounts["site"].is_active = False
    elif boundary == "two_sites":
        db_session.add(ParkingSite(name="Historical lot", is_active=False))
    elif boundary == "no_membership":
        db_session.delete(member)
    else:
        member.role = "staff"
    db_session.commit()
    before = db_session.query(User).count()
    response = client.post("/api/v1/users", headers=_headers(accounts["manager"]), json=_create_payload(accounts))
    assert response.status_code == (409 if boundary == "no_site" else 403), response.text
    assert db_session.query(User).count() == before


def test_membership_failure_rolls_back_new_staff_account(client, db_session, accounts):
    def fail_membership(*args):
        raise IntegrityError("membership failed", {}, Exception("test failure"))

    event.listen(SiteMembership, "before_insert", fail_membership)
    try:
        response = client.post("/api/v1/users", headers=_headers(accounts["manager"]), json=_create_payload(accounts))
    finally:
        event.remove(SiteMembership, "before_insert", fail_membership)
    assert response.status_code == 409
    assert db_session.scalar(select(User).where(User.username == "new_staff_account")) is None


def test_admin_keeps_full_user_management(client, accounts):
    headers = _headers(accounts["admin"])
    response = client.post("/api/v1/users", headers=headers,
                           json=_create_payload(accounts, username="admin_created_manager", role_id=accounts["roles"]["manager"].id))
    assert response.status_code == 201, response.text
    url = f"/api/v1/users/{response.json()['id']}"
    assert client.put(url, headers=headers, json={"is_active": False}).status_code == 200
    assert client.delete(url, headers=headers).status_code == 204


def test_staff_promoted_before_mutation_is_rechecked_after_lock(client, db_session, accounts, monkeypatch):
    original_lock = user_router._lock_user
    staff_id = accounts["staff"].id
    admin_role_id = accounts["roles"]["admin"].id

    def promote_before_lock(db, user_id):
        if user_id == staff_id:
            # Simulate a concurrent admin action after authentication while
            # the request's identity map still contains the old staff role.
            db.execute(update(User).where(User.id == staff_id).values(role_id=admin_role_id)
                       .execution_options(synchronize_session=False))
            db.commit()
        return original_lock(db, user_id)

    monkeypatch.setattr(user_router, "_lock_user", promote_before_lock)
    response = client.put(f"/api/v1/users/{staff_id}", headers=_headers(accounts["manager"]), json={"is_active": False})
    assert response.status_code == 403
    db_session.refresh(accounts["staff"])
    assert accounts["staff"].role_id == admin_role_id
    assert accounts["staff"].is_active is True


@pytest.mark.parametrize("field", ("username", "full_name", "role_id", "is_active"))
def test_manager_cannot_clear_required_staff_fields(client, db_session, accounts, field):
    response = client.put(f"/api/v1/users/{accounts['staff'].id}", headers=_headers(accounts["manager"]), json={field: None})
    assert response.status_code == 422
    db_session.refresh(accounts["staff"])
    assert getattr(accounts["staff"], field) is not None
