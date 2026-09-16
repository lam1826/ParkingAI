"""Customer support threads: ownership, site scope, manager replies and notifications."""
from sqlalchemy import select

from expansion.portal_models import PortalAccountLink, PortalNotification
from expansion.site_models import ParkingSite, SiteMembership
from expansion.support_router import router as support_router
from models.customer import Customer
from models.role import Role
from models.user import User
from test_portal_api import onboard, portal  # noqa: F401


def _app(portal):
    client, current, users, site, kind, db = portal
    client.app.include_router(support_router, prefix="/api/v2")
    return client, current, users, site, db


def _manager_of_other_site(db):
    role = db.scalar(select(Role).where(Role.name == "manager"))
    if role is None:
        role = Role(name="manager")
        db.add(role)
        db.flush()
    other = ParkingSite(name="Bãi khác")
    db.add(other)
    db.flush()
    manager = User(username="manager_other", full_name="Manager other", password_hash="unused", role_id=role.id, is_active=True)
    db.add(manager)
    db.flush()
    db.add(SiteMembership(site_id=other.id, user_id=manager.id, role="manager"))
    db.commit()
    return manager, other


def test_support_thread_round_trip_with_notifications_and_close(portal):
    client, current, users, site, db = _app(portal)
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    created = client.post("/api/v2/me/support-requests", json={"subject": "Hỏi về vé tháng", "category": "order",
        "message": "Vé của tôi chưa kích hoạt?", "linked_type": "order", "linked_id": order["id"]})
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["status"] == "open" and ticket["site_id"] == site.id and ticket["messages"][0]["mine"] is True
    assert client.get("/api/v2/me/support-requests").json()["items"][0]["id"] == ticket["id"]
    # Manager (global admin here) answers; the customer gets one in-app notification per reply.
    current["user"] = users[0]
    listed = client.get(f"/api/v2/sites/{site.id}/support-requests", params={"status": "open"}).json()["items"]
    assert [row["id"] for row in listed] == [ticket["id"]] and listed[0]["customer_name"] == "Khách A"
    answered = client.post(f"/api/v2/sites/{site.id}/support-requests/{ticket['id']}/messages", json={"body": "Đã kích hoạt, mời kiểm tra."})
    assert answered.status_code == 200 and answered.json()["status"] == "answered"
    assert answered.json()["messages"][-1]["author_role"] == "admin" and answered.json()["requester_username"] == "customer"
    current["user"] = users[1]
    detail = client.get(f"/api/v2/me/support-requests/{ticket['id']}").json()
    assert [m["author_role"] for m in detail["messages"]] == ["customer", "admin"]
    notices = client.get("/api/v2/me/notifications").json()["items"]
    assert any("phản hồi" in row["message"] for row in notices)
    replied = client.post(f"/api/v2/me/support-requests/{ticket['id']}/messages", json={"body": "Cảm ơn, đã thấy."})
    assert replied.json()["status"] == "open"
    current["user"] = users[0]
    closed = client.post(f"/api/v2/sites/{site.id}/support-requests/{ticket['id']}/close", json={"note": "Đã xử lý xong."})
    assert closed.json()["status"] == "closed" and closed.json()["closed_at"] is not None
    assert client.post(f"/api/v2/sites/{site.id}/support-requests/{ticket['id']}/messages", json={"body": "x"}).status_code == 409
    current["user"] = users[1]
    assert client.post(f"/api/v2/me/support-requests/{ticket['id']}/messages", json={"body": "Còn nữa"}).status_code == 409
    assert client.get("/api/v2/me/support-requests", params={"status": "closed"}).json()["items"][0]["id"] == ticket["id"]
    assert db.scalar(select(PortalNotification).where(PortalNotification.event_key == f"support:{ticket['id']}:closed")) is not None


def test_customer_cannot_read_or_link_another_customer_and_scope_is_enforced(portal):
    client, current, users, site, db = _app(portal)
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    mine = client.post("/api/v2/me/support-requests", json={"subject": "Của tôi", "message": "..."}).json()
    # Another verified customer.
    current["user"] = users[2]
    assert client.get("/api/v2/me/support-requests").status_code == 409  # not linked yet
    assert client.post("/api/v2/me/profile", json={"full_name": "Khách B", "phone_number": "0909999999"}).status_code == 200
    assert client.get(f"/api/v2/me/support-requests/{mine['id']}").status_code == 404
    assert client.post(f"/api/v2/me/support-requests/{mine['id']}/messages", json={"body": "hack"}).status_code == 404
    assert client.post("/api/v2/me/support-requests", json={"subject": "Gắn đơn người khác", "message": "x",
        "linked_type": "order", "linked_id": order["id"]}).status_code == 404
    assert client.post("/api/v2/me/support-requests", json={"subject": "Thiếu id", "message": "x", "linked_type": "order"}).status_code == 422
    assert client.get("/api/v2/me/support-requests").json()["items"] == []
    # A manager of a different site sees nothing of this site.
    manager, other = _manager_of_other_site(db)
    current["user"] = manager
    assert client.get(f"/api/v2/sites/{site.id}/support-requests").status_code == 403
    assert client.get(f"/api/v2/sites/{other.id}/support-requests").json()["items"] == []
    assert client.post(f"/api/v2/sites/{site.id}/support-requests/{mine['id']}/messages", json={"body": "x"}).status_code == 403
    # Customers cannot use manager routes even for their own site.
    current["user"] = users[1]
    assert client.get(f"/api/v2/sites/{site.id}/support-requests").status_code == 403
    # Only the customer may close their own request; the closer is recorded.
    closed = client.post(f"/api/v2/me/support-requests/{mine['id']}/close")
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    customer = db.scalar(select(Customer).join(PortalAccountLink, PortalAccountLink.customer_id == Customer.id)
        .where(PortalAccountLink.user_id == users[1].id))
    assert customer.full_name == "Khách A"
