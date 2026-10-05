"""CL-ONLINE fixes 05/10: portal review actions, request corrections and decision notes (#52, #53, #54)."""
from sqlalchemy import select

from expansion.portal_models import PortalLinkRequest, PortalNotification, PortalOrder, PortalVehicleRequest
from models.customer import Customer

from test_portal_api import portal, onboard  # noqa: F401
from test_timed_parking import timed  # noqa: F401


def _admin_row(client, current, users, order_id):
    current["user"] = users[0]
    return next(row for row in client.get("/api/v2/portal/admin/orders").json()["items"] if row["id"] == order_id)


# --- #52 -----------------------------------------------------------------

def test_timed_demo_review_order_offers_only_reject(timed, monkeypatch):
    portal_, body, slot, rate = timed
    client, current, users, site, kind, db = portal_
    order = client.post("/api/v2/me/orders", json=body).json()
    deadline = db.get(PortalOrder, order["id"]).expires_at
    monkeypatch.setattr("expansion.portal_service.business_now", lambda: deadline)
    monkeypatch.setattr("expansion.timed_parking_service.business_now", lambda: deadline)
    client.post(f"/api/v2/me/orders/{order['id']}/simulate", json=dict(token=order["demo_token"], outcome="success"))
    assert db.get(PortalOrder, order["id"]).status == "review"
    row = _admin_row(client, current, users, order["id"])
    assert row["review_actions"] == ["reject"]
    approve = client.post(f"/api/v2/portal/admin/orders/{order['id']}/review", json={"approve": True, "note": "Đã kiểm tra"})
    assert approve.status_code == 409 and "từ chối" in approve.json()["detail"]
    reject = client.post(f"/api/v2/portal/admin/orders/{order['id']}/review", json={"approve": False, "note": "Hết giữ chỗ"})
    assert reject.status_code == 200 and reject.json()["status"] == "cancelled"


def test_monthly_demo_review_order_keeps_approve_and_reject(portal):
    client, current, users, site, kind, db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    row = db.get(PortalOrder, order["id"])
    row.status, row.review_reason = "review", "late_payment"
    db.commit()
    assert _admin_row(client, current, users, order["id"])["review_actions"] == ["approve", "reject"]
    row.status = "pending"
    db.commit()
    assert _admin_row(client, current, users, order["id"])["review_actions"] == []


# --- #53 -----------------------------------------------------------------

def test_corrected_link_request_is_rejected_not_silently_dropped(portal):
    client, current, users, site, kind, db = portal
    first = client.post("/api/v2/me/link-requests", json={"phone_number": "0911000111", "note": "Sai số"})
    assert first.status_code == 200, first.text
    retry = client.post("/api/v2/me/link-requests", json={"phone_number": "0911000111", "note": "Sai số"})
    assert retry.status_code == 200 and retry.json()["id"] == first.json()["id"]
    corrected = client.post("/api/v2/me/link-requests", json={"phone_number": "0911000222", "note": "Số đúng"})
    assert corrected.status_code == 409
    assert "đang chờ" in corrected.json()["detail"]
    assert db.get(PortalLinkRequest, first.json()["id"]).phone_number == "0911000111"
    listing = client.get("/api/v2/me/link-requests").json()["items"]
    assert listing[0]["phone_number"] == "0911000111" and listing[0]["note"] == "Sai số"


def test_corrected_vehicle_request_is_rejected_not_silently_dropped(portal):
    from models.vehicle_type import VehicleType
    client, current, users, site, kind, db = portal
    other = VehicleType(name="Ô tô CL", requires_plate=True, is_active=True)
    db.add(other)
    db.commit()
    assert client.post("/api/v2/me/profile", json={"full_name": "Khách A", "phone_number": "0901234567"}).status_code == 200
    first = client.post("/api/v2/me/vehicle-requests", json={"license_plate": "30A-12345", "vehicle_type_id": kind.id})
    assert first.status_code == 200, first.text
    retry = client.post("/api/v2/me/vehicle-requests", json={"license_plate": "30A-12345", "vehicle_type_id": kind.id})
    assert retry.status_code == 200 and retry.json()["id"] == first.json()["id"]
    corrected = client.post("/api/v2/me/vehicle-requests", json={"license_plate": "30A-12345", "vehicle_type_id": other.id})
    assert corrected.status_code == 409
    assert db.get(PortalVehicleRequest, first.json()["id"]).vehicle_type_id == kind.id


# --- #54 -----------------------------------------------------------------

def test_vehicle_rejection_reason_reaches_the_customer(portal):
    client, current, users, site, kind, db = portal
    assert client.post("/api/v2/me/profile", json={"full_name": "Khách A", "phone_number": "0901234567"}).status_code == 200
    request = client.post("/api/v2/me/vehicle-requests", json={"license_plate": "30A-12345", "vehicle_type_id": kind.id})
    current["user"] = users[0]
    url = f"/api/v2/portal/admin/vehicle-requests/{request.json()['id']}/resolve"
    assert client.post(url, json={"approve": False}).status_code == 422
    rejected = client.post(url, json={"approve": False, "note": "Biển số không khớp giấy đăng ký"})
    assert rejected.status_code == 200, rejected.text
    current["user"] = users[1]
    messages = [row["message"] for row in client.get("/api/v2/me/notifications").json()["items"]]
    assert any("Biển số không khớp giấy đăng ký" in message for message in messages)


def test_link_approval_note_reaches_the_customer(portal):
    client, current, users, site, kind, db = portal
    customer = Customer(full_name="Hồ sơ có sẵn", phone_number="0911222333")
    db.add(customer)
    db.commit()
    request = client.post("/api/v2/me/link-requests", json={"phone_number": customer.phone_number})
    current["user"] = users[0]
    url = f"/api/v2/portal/admin/link-requests/{request.json()['id']}/resolve"
    approved = client.post(url, json={"approve": True, "note": "Đã gọi xác minh qua số điện thoại"})
    assert approved.status_code == 200, approved.text
    note = db.scalar(select(PortalNotification).where(PortalNotification.customer_id == customer.id))
    assert "Đã gọi xác minh qua số điện thoại" in note.message


def test_link_rejection_does_not_demand_a_reason_it_cannot_keep(portal):
    # The requester has no customer profile, so no notification can carry a reason:
    # the reason is optional (the UI labels it as not stored) instead of required-then-dropped.
    client, current, users, site, kind, db = portal
    request = client.post("/api/v2/me/link-requests", json={"phone_number": "0911222444"})
    current["user"] = users[0]
    url = f"/api/v2/portal/admin/link-requests/{request.json()['id']}/resolve"
    rejected = client.post(url, json={"approve": False})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
