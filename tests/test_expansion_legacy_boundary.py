"""A site membership must not be bypassed using a pre-expansion API path."""
import pytest

from expansion.site_models import ParkingSite, SiteMembership
from models.role import Role
from services.auth_service import get_current_user
from main import app


@pytest.mark.parametrize("path", ["/api/v1/customers", "/api/v1/vehicles", "/api/v1/payments", "/api/v1/parking-sessions"])
def test_multisite_staff_cannot_use_global_routes(client, db_session, test_user, path):
    a, b = ParkingSite(name="Allowed"), ParkingSite(name="Closed history", is_active=False)
    db_session.add_all([a, b]); db_session.flush()
    db_session.add(SiteMembership(site_id=a.id, user_id=test_user.id, role="manager"))
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    assert client.get(path).status_code == 403
    capabilities = client.get("/api/v2/system/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["legacy_workspace_allowed"] is False
    scoped = client.get("/api/v2/sites")
    assert scoped.status_code == 200
    assert [row["id"] for row in scoped.json()] == [a.id]


def test_single_site_requires_membership_but_global_admin_can_manage(client, db_session, test_user):
    site = ParkingSite(name="One site")
    db_session.add(site); db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    assert client.get("/api/v1/vehicles").status_code == 403
    db_session.add(SiteMembership(site_id=site.id, user_id=test_user.id, role="staff")); db_session.commit()
    assert client.get("/api/v1/vehicles").status_code == 200
    role = Role(name="admin"); db_session.add(role); db_session.flush()
    test_user.role = role
    db_session.add(ParkingSite(name="Other site")); db_session.commit()
    assert client.get("/api/v2/system/capabilities").json()["legacy_workspace_allowed"] is True
    assert client.get("/api/v1/vehicles").status_code == 200


def test_customer_capabilities_cannot_enable_global_workspace(client, db_session, test_user):
    role = Role(name="customer"); db_session.add(role); db_session.flush()
    test_user.role = role; db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    assert client.get("/api/v2/system/capabilities").json()["legacy_workspace_allowed"] is False
    assert client.get("/api/v1/vehicles").status_code == 403


def test_global_manager_demoted_at_only_site_cannot_bypass_site_role(client, db_session, test_user):
    role = Role(name="manager"); site = ParkingSite(name="One site")
    db_session.add_all([role, site]); db_session.flush()
    test_user.role = role
    db_session.add(SiteMembership(site_id=site.id, user_id=test_user.id, role="staff")); db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: test_user
    assert client.get("/api/v2/system/capabilities").json()["legacy_workspace_allowed"] is False
    assert client.get("/api/v1/users").status_code == 403
