"""CL-ONLINE fix 05/10 (#21): portal admin lists follow manager membership, not any membership."""
from sqlalchemy import select

from expansion.portal_models import SubscriptionPlan
from expansion.site_models import SiteMembership
from models.role import Role
from models.user import User

from test_portal_api import onboard, portal  # noqa: F401
from test_refund_requests import _app, _collected_manual_order


def _manager(db, name, site_id, membership_role):
    role = db.scalar(select(Role).where(Role.name == "manager"))
    if role is None:
        role = Role(name="manager")
        db.add(role)
        db.flush()
    actor = User(username=name, full_name=name, role_id=role.id, password_hash="unused", is_active=True)
    db.add(actor)
    db.flush()
    db.add(SiteMembership(user_id=actor.id, site_id=site_id, role=membership_role))
    db.commit()
    return actor


def _scenario(portal):
    client, current, users, site, db = _app(portal)
    collected = _collected_manual_order(portal, key="clonline-scope-collected")
    created = client.post(f"/api/v2/me/orders/{collected['id']}/refund-requests", json={"reason": "Khách đổi ý"})
    assert created.status_code in (200, 201), created.text
    plan_id = db.scalar(select(SubscriptionPlan.id))
    vehicle_id = client.get("/api/v2/me/vehicles").json()["items"][0]["id"]
    pending = client.post("/api/v2/me/orders", json={"plan_id": plan_id, "vehicle_id": vehicle_id,
        "idempotency_key": "clonline-scope-pending", "payment_mode": "manual"})
    assert pending.status_code == 200, pending.text
    return client, current, site, db


def test_manager_with_staff_membership_sees_no_site_orders_refunds_or_plans(portal):
    client, current, site, db = _scenario(portal)
    current["user"] = _manager(db, "clonline-demoted-manager", site.id, "staff")
    assert client.get("/api/v2/portal/admin/orders").json()["items"] == []
    assert client.get("/api/v2/portal/admin/refund-requests").json()["items"] == []
    assert client.get("/api/v2/portal/admin/plans").json()["items"] == []


def test_manager_with_manager_membership_still_sees_site_rows(portal):
    client, current, site, db = _scenario(portal)
    current["user"] = _manager(db, "clonline-site-manager", site.id, "manager")
    assert len(client.get("/api/v2/portal/admin/orders").json()["items"]) == 2
    assert len(client.get("/api/v2/portal/admin/refund-requests").json()["items"]) == 1
    assert len(client.get("/api/v2/portal/admin/plans").json()["items"]) == 1
