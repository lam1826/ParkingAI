"""Review 05/10/2026 #20, #65: customer support routing and closure notifications.

#20 A ticket linked to a resource whose site is inactive would be unreachable for
    every manager and admin: it is refused with a clear message (the linked site
    stays authoritative, DECISIONS 2026-09-27). A linked resource without a site
    is accepted with the site the customer chose (the panel now sends it).
#65 Every manager closure notifies the customer, including a re-close after reopen.
"""
from sqlalchemy import func, select

from expansion.portal_models import PortalNotification
from expansion.site_models import ParkingSite
from expansion.support_models import CustomerSupportRequest
from expansion.support_router import router as support_router
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.vehicle import Vehicle
from services.payment_service import PaymentService
from core.clock import business_now
from datetime import timedelta
from test_portal_api import onboard, portal  # noqa: F401


def _app(portal):
    client = portal[0]
    client.app.include_router(support_router, prefix="/api/v2")
    return portal


def test_link_to_an_inactive_site_is_refused_instead_of_lost(portal):
    client, current, users, site, kind, db = _app(portal)
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    other = ParkingSite(name="Bãi còn hoạt động", is_active=True)
    db.add(other)
    site.is_active = False
    db.commit()
    body = {"subject": "Đơn ở bãi đã đóng", "message": "Hoàn giúp", "category": "order", "linked_type": "order", "linked_id": order["id"]}
    refused = client.post("/api/v2/me/support-requests", json=body)
    assert refused.status_code == 409, refused.text
    assert "ngừng hoạt động" in refused.json()["detail"]
    assert client.post("/api/v2/me/support-requests", json={**body, "site_id": other.id}).status_code == 409
    assert db.scalar(select(func.count()).select_from(CustomerSupportRequest)) == 0
    # Without the link the customer reaches the active site.
    plain = client.post("/api/v2/me/support-requests", json={"subject": "Đơn ở bãi đã đóng", "message": "Mã đơn " + order["id"][:8],
        "site_id": other.id})
    assert plain.status_code == 201 and plain.json()["site_id"] == other.id


def test_site_less_linked_receipt_goes_to_the_chosen_site_with_two_active_sites(portal):
    client, current, users, site, kind, db = _app(portal)
    onboard(portal)
    customer = db.scalar(select(Customer).where(Customer.full_name == "Khách A"))
    vehicle = db.scalar(select(Vehicle).where(Vehicle.customer_id == customer.id))
    start = business_now().date() + timedelta(days=40)
    period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=200000, start_date=start,
        end_date=start + timedelta(days=29), pass_code="SUPPORT-HIST-0001")
    db.add(period)
    db.flush()
    receipt = PaymentService.record_receipt(db, "monthly_pass", period.id, 200000, None, "cash")
    other = ParkingSite(name="Bãi thứ hai", is_active=True)
    db.add(other)
    db.commit()
    assert receipt.site_id is None
    body = {"subject": "Vé tháng", "message": "Giúp", "category": "receipt", "linked_type": "receipt", "linked_id": receipt.id}
    assert client.post("/api/v2/me/support-requests", json=body).status_code == 422
    created = client.post("/api/v2/me/support-requests", json={**body, "site_id": other.id})
    assert created.status_code == 201 and created.json()["site_id"] == other.id, created.text


def test_every_manager_closure_notifies_the_customer(portal):
    client, current, users, site, kind, db = _app(portal)
    onboard(portal)
    created = client.post("/api/v2/me/support-requests", json={"subject": "Hỏi về vé", "message": "Xin chào", "site_id": site.id})
    assert created.status_code == 201, created.text
    ticket = created.json()
    current["user"] = users[0]
    base = f"/api/v2/sites/{site.id}/support-requests/{ticket['id']}"
    assert client.post(f"{base}/close", json={"note": ""}).status_code == 200
    assert client.post(f"{base}/close", json={"note": ""}).status_code == 200  # replay: no extra notice
    assert client.post(f"{base}/reopen").status_code == 200
    assert client.post(f"{base}/messages", json={"body": "Bổ sung"}).status_code == 200
    assert client.post(f"{base}/close", json={"note": "Đóng lại"}).json()["status"] == "closed"
    assert client.post(f"{base}/reopen").status_code == 200
    assert client.post(f"{base}/close", json={"note": ""}).status_code == 200
    keys = sorted(db.scalars(select(PortalNotification.event_key).where(
        PortalNotification.event_key.like(f"support:{ticket['id']}:closed%"))))
    assert keys == [f"support:{ticket['id']}:closed", f"support:{ticket['id']}:closed:2", f"support:{ticket['id']}:closed:3"]
    current["user"] = users[1]
    notices = [row["message"] for row in client.get("/api/v2/me/notifications").json()["items"]]
    assert sum(1 for message in notices if "đã được quản lý đóng" in message) == 3


def test_global_admin_sees_open_requests_filed_at_other_sites(portal):
    """Rework of #76: requests filed under a site the single-site screen never opens.

    The admin's queue for the working site lists, read-only from the server
    side, the open refund and support requests of every other site (active or
    closed) with the site name, so they are never lost. Other users get nothing.
    """
    from expansion.site_models import SiteMembership
    from models.role import Role
    from models.user import User
    client, current, users, site, kind, db = _app(portal)
    work = ParkingSite(name="Bãi đang dùng", is_active=True)
    db.add(work)
    db.commit()
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    paid = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"}).json()
    refund = client.post(f"/api/v2/me/receipts/{paid['receipt_id']}/refund-requests", json={"reason": "Không dùng nữa"})
    assert refund.status_code == 201 and refund.json()["site_id"] == site.id, refund.text
    ticket = client.post("/api/v2/me/support-requests", json={"subject": "Hỏi về đơn", "message": "Giúp tôi",
        "category": "order", "linked_type": "order", "linked_id": order["id"]})
    assert ticket.status_code == 201 and ticket.json()["site_id"] == site.id, ticket.text
    here = client.post("/api/v2/me/support-requests", json={"subject": "Ở bãi đang dùng", "message": "Xin chào", "site_id": work.id})
    assert here.status_code == 201, here.text
    closed = client.post("/api/v2/me/support-requests", json={"subject": "Đã xong", "message": "Cảm ơn", "site_id": site.id}).json()
    current["user"] = users[0]
    assert client.post(f"/api/v2/sites/{site.id}/support-requests/{closed['id']}/close", json={"note": ""}).status_code == 200
    # The working site's own queues stay as they were.
    assert client.get(f"/api/v2/sites/{work.id}/refund-requests").json()["items"] == []
    elsewhere = client.get(f"/api/v2/sites/{work.id}/other-site-requests")
    assert elsewhere.status_code == 200, elsewhere.text
    data = elsewhere.json()
    assert data["visible"] is True
    assert [(row["id"], row["site_id"], row["site_name"], row["site_active"]) for row in data["refund_requests"]] == [
        (refund.json()["id"], site.id, site.name, True)]
    assert data["refund_requests"][0]["customer_name"] == "Khách A"
    assert [(row["id"], row["site_id"], row["site_active"]) for row in data["support_requests"]] == [(ticket.json()["id"], site.id, True)]
    # The listed refund can be handled at its own site by the admin.
    reviewed = client.post(f"/api/v2/sites/{site.id}/refund-requests/{refund.json()['id']}/review", json={"note": ""})
    assert reviewed.status_code == 200, reviewed.text
    # A closed site keeps its open requests visible (they cannot be opened there any more).
    site.is_active = False
    db.commit()
    data = client.get(f"/api/v2/sites/{work.id}/other-site-requests").json()
    assert [(row["id"], row["status"], row["site_active"]) for row in data["refund_requests"]] == [(refund.json()["id"], "reviewing", False)]
    assert [row["site_active"] for row in data["support_requests"]] == [False]
    # A site manager is not a global admin: nothing from other sites is exposed.
    manager_role = db.scalar(select(Role).where(Role.name == "manager"))
    if manager_role is None:
        manager_role = Role(name="manager")
        db.add(manager_role)
        db.flush()
    manager = User(username="manager-work", full_name="Quản lý bãi đang dùng", password_hash="unused", role_id=manager_role.id, is_active=True)
    db.add(manager)
    db.flush()
    db.add(SiteMembership(site_id=work.id, user_id=manager.id, role="manager"))
    db.commit()
    current["user"] = manager
    hidden = client.get(f"/api/v2/sites/{work.id}/other-site-requests")
    assert hidden.status_code == 200 and hidden.json() == {"visible": False, "refund_requests": [], "support_requests": []}
