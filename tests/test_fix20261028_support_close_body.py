"""Review 28/10/2026 A-12: closing a support request never needs a body.

The manager note is optional, so a close without any body, with ``{}`` and with
a note all work; the customer close keeps working without a body. Unknown keys
are still refused (the input model forbids extras).
"""
from sqlalchemy import select

from expansion.support_models import CustomerSupportMessage
from expansion.support_router import router as support_router
from test_portal_api import onboard, portal  # noqa: F401


def _ticket(portal, subject):
    client, current, users, site, kind, db = portal
    created = client.post("/api/v2/me/support-requests", json={"subject": subject, "message": "Xin chào", "site_id": site.id})
    assert created.status_code == 201, created.text
    return created.json()


def test_manager_close_accepts_no_body_an_empty_body_and_a_note(portal):
    client, current, users, site, kind, db = portal
    client.app.include_router(support_router, prefix="/api/v2")
    onboard(portal)
    plain, empty, noted = (_ticket(portal, name) for name in ("Không gửi nội dung", "Gửi rỗng", "Kèm ghi chú"))
    current["user"] = users[0]
    base = f"/api/v2/sites/{site.id}/support-requests"
    closed = client.post(f"{base}/{plain['id']}/close")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert client.post(f"{base}/{plain['id']}/close").status_code == 200  # replay
    closed = client.post(f"{base}/{empty['id']}/close", json={})
    assert closed.status_code == 200 and closed.json()["status"] == "closed", closed.text
    closed = client.post(f"{base}/{noted['id']}/close", json={"note": "Đã giải quyết tại quầy"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed", closed.text
    notes = db.scalars(select(CustomerSupportMessage.body).where(CustomerSupportMessage.request_id == noted["id"])).all()
    assert "Đã giải quyết tại quầy" in notes
    # A body without a note adds no message; unknown keys stay refused.
    assert db.scalars(select(CustomerSupportMessage.body).where(CustomerSupportMessage.request_id == plain["id"])).all() == ["Xin chào"]
    assert client.post(f"{base}/{noted['id']}/close", json={"reason": "x"}).status_code == 422


def test_customer_close_still_works_without_a_body(portal):
    client, current, users, site, kind, db = portal
    client.app.include_router(support_router, prefix="/api/v2")
    onboard(portal)
    ticket = _ticket(portal, "Khách tự đóng")
    closed = client.post(f"/api/v2/me/support-requests/{ticket['id']}/close")
    assert closed.status_code == 200 and closed.json()["status"] == "closed", closed.text
