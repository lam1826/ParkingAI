"""Portal contracts run in a separate application and an isolated SQLite database."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import expansion.site_models  # register referenced site metadata
from expansion.gateway import PortalSettings
from expansion.portal_models import PortalAccountLink, PortalOrder, PortalSessionGrant
from expansion.portal_router import router
from expansion.portal_service import capture_session_ownership
from database import get_db
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.parking_session import ParkingSession
from expansion.site_models import ParkingSite
from services.auth_service import get_current_user


@pytest.fixture
def portal(db_session, vehicle_type, monkeypatch):
    monkeypatch.setenv("DEMO_PAYMENTS_ENABLED", "true")
    # Never read payment credentials, never construct an external payment client.
    monkeypatch.setattr("expansion.gateway.PortalSettings", lambda: PortalSettings(_env_file=None, DEMO_PAYMENTS_ENABLED=True))
    users = []
    for name in ["admin", "customer", "customer2"]:
        role_name = "customer" if name.startswith("customer") else "admin"
        role = db_session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()
        user = User(username=name, full_name=name, password_hash="unused", role_id=role.id, is_active=True)
        db_session.add(user)
        db_session.flush()
        users.append(user)
    site = ParkingSite(name="Demo Site")
    db_session.add(site)
    db_session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v2")
    app.dependency_overrides[get_db] = lambda: db_session
    current = {"user": users[1]}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    with TestClient(app) as client:
        yield client, current, users, site, vehicle_type, db_session


def onboard(portal):
    client, current, users, site, vehicle_type, db = portal
    assert client.post("/api/v2/me/profile", json={"full_name": "Khách A", "phone_number": "0901234567"}).status_code == 200
    request = client.post("/api/v2/me/vehicle-requests", json={"license_plate": "30A-12345", "vehicle_type_id": vehicle_type.id})
    assert request.status_code == 200, request.text
    current["user"] = users[0]
    approved = client.post(f"/api/v2/portal/admin/vehicle-requests/{request.json()['id']}/resolve", json={"approve": True})
    assert approved.status_code == 200, approved.text
    plan = client.post("/api/v2/portal/admin/plans", json={"name": "30 ngày", "site_id": site.id,
        "vehicle_type_id": vehicle_type.id, "duration_days": 30, "price": 300000})
    assert plan.status_code == 200, plan.text
    current["user"] = users[1]
    vehicles = client.get("/api/v2/me/vehicles").json()["items"]
    return {"plan_id": plan.json()["id"], "vehicle_id": vehicles[0]["id"], "idempotency_key": "purchase-0001"}


def test_new_profile_does_not_claim_existing_phone_or_reveal_other_customer(portal):
    client, current, users, *_ = portal
    result = client.post("/api/v2/me/profile", json={"full_name": "Khách A", "phone_number": "0901234567"})
    assert result.status_code == 200
    current["user"] = users[2]
    duplicate = client.post("/api/v2/me/profile", json={"full_name": "Người khác", "phone_number": "0901234567"})
    assert duplicate.status_code == 409
    assert "Khách A" not in duplicate.text
    assert client.get("/api/v2/me/profile").json()["linked"] is False
    assert client.get("/api/v2/me/vehicles").status_code == 409


def test_customer_cannot_self_approve_vehicle_or_forge_server_order_price(portal):
    body = onboard(portal)
    client = portal[0]
    assert client.get("/api/v2/portal/admin/vehicle-requests").status_code == 403
    forged = client.post("/api/v2/me/orders", json={**body, "amount": 1})
    assert forged.status_code == 422


def test_reviewer_cannot_approve_own_profile_link_request(portal):
    client, current, users, *_rest, db = portal
    customer = Customer(full_name="Hồ sơ có sẵn", phone_number="0911222333")
    db.add(customer)
    db.commit()
    current["user"] = users[0]
    request = client.post("/api/v2/me/link-requests", json={"phone_number": customer.phone_number})
    assert request.status_code == 200

    result = client.post(
        f"/api/v2/portal/admin/link-requests/{request.json()['id']}/resolve",
        json={"approve": True},
    )

    assert result.status_code == 403
    assert db.scalar(select(PortalAccountLink).where(PortalAccountLink.user_id == users[0].id)) is None


def test_reviewer_cannot_approve_vehicle_for_own_linked_profile(portal):
    client, current, users, _site, kind, db = portal
    current["user"] = users[0]
    assert client.post("/api/v2/me/profile", json={
        "full_name": "Quản trị viên",
        "phone_number": "0911333444",
    }).status_code == 200
    request = client.post("/api/v2/me/vehicle-requests", json={
        "license_plate": "51A-SELF01",
        "vehicle_type_id": kind.id,
    })
    assert request.status_code == 200

    result = client.post(
        f"/api/v2/portal/admin/vehicle-requests/{request.json()['id']}/resolve",
        json={"approve": True},
    )

    assert result.status_code == 403
    assert db.scalar(select(Vehicle).where(Vehicle.license_plate == "51A-SELF01")) is None


def test_admin_can_unlink_a_portal_account_without_deleting_customer(portal):
    client, current, users, *_rest, db = portal
    client.post("/api/v2/me/profile", json={"full_name": "Khách A", "phone_number": "0901234567"})
    customer_id = client.get("/api/v2/me/profile").json()["customer"]["id"]
    current["user"] = users[0]

    links = client.get("/api/v2/portal/admin/account-links")
    assert links.status_code == 200
    assert links.json()["items"][0]["requester_role"] == "customer"
    removed = client.delete(f"/api/v2/portal/admin/account-links/{users[1].id}")

    assert removed.status_code == 204
    assert db.get(Customer, customer_id) is not None
    current["user"] = users[1]
    assert client.get("/api/v2/me/profile").json()["linked"] is False


def test_demo_success_is_atomic_idempotent_and_never_records_real_money(portal):
    body = onboard(portal)
    client, current, users, site, kind, db = portal
    order = client.post("/api/v2/me/orders", json=body).json()
    assert order["amount"] == 300000
    assert order["demo_payload"].startswith("PARKINGAI-DEMO:")
    assert "<svg" in order["demo_qr_svg"]
    assert client.get(f"/api/v2/me/orders/{order['id']}").json()["demo_token"] == order["demo_token"]
    confirmed = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "fulfilled"
    replay = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert replay.json()["receipt_id"] == confirmed.json()["receipt_id"]
    assert len(client.get("/api/v2/me/passes").json()["items"]) == 1
    receipts = client.get("/api/v2/me/receipts").json()["items"]
    assert len(receipts) == 1 and receipts[0]["method"] == "demo"
    receipt = db.get(Payment, receipts[0]["id"])
    assert receipt.collected_by_id is None and receipt.shift_id is None
    from services.payment_service import PaymentService
    from core.clock import business_now
    now = business_now()
    assert PaymentService.revenue_breakdown(db, now - timedelta(days=1), now + timedelta(days=1))["total_revenue"] == 0


def test_demo_token_and_order_ownership_are_both_required(portal):
    client, current, users, *_ = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    endpoint = f"/api/v2/me/orders/{order['id']}/simulate"
    assert client.post(endpoint, json={"token": "x" * 43, "outcome": "success"}).status_code == 403
    current["user"] = users[2]
    client.post("/api/v2/me/profile", json={"full_name": "Khách B", "phone_number": "0907654321"})
    assert client.get(f"/api/v2/me/orders/{order['id']}").status_code == 404
    assert client.post(endpoint, json={"token": order["demo_token"], "outcome": "success"}).status_code == 404
    assert client.get("/api/v2/me/receipts").json()["items"] == []


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_demo_failure_or_cancel_never_issues_pass_and_cannot_turn_into_success(portal, outcome):
    client = portal[0]
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    endpoint = f"/api/v2/me/orders/{order['id']}/simulate"
    result = client.post(endpoint, json={"token": order["demo_token"], "outcome": outcome})
    assert result.status_code == 200 and result.json()["status"] == outcome
    assert client.post(endpoint, json={"token": order["demo_token"], "outcome": "success"}).status_code == 409
    assert client.get("/api/v2/me/passes").json()["items"] == []
    assert client.get("/api/v2/me/receipts").json()["items"] == []


def test_late_demo_success_is_reviewed_without_activating_pass(portal):
    client, *_, db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    db.get(PortalOrder, order["id"]).expires_at -= timedelta(hours=1)
    db.commit()
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert result.status_code == 200 and result.json()["status"] == "review"
    assert result.json()["review_reason"] == "late_payment"
    assert client.get("/api/v2/me/passes").json()["items"] == []


def test_demo_refund_requires_manager_and_is_only_compensating_demo_ledger(portal):
    client, current, users, site, kind, db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    refund = client.post(f"/api/v2/me/orders/{order['id']}/refund-requests", json={"reason": "Thử hoàn tiền đồ án"}).json()
    assert len(client.get("/api/v2/me/receipts").json()["items"]) == 1
    url = f"/api/v2/portal/admin/refund-requests/{refund['id']}/resolve"
    assert client.post(url, json={"approve": True}).status_code == 403
    current["user"] = users[0]
    result = client.post(url, json={"approve": True})
    assert result.status_code == 200, result.text
    replay = client.post(url, json={"approve": True})
    assert replay.json()["refund_payment_id"] == result.json()["refund_payment_id"]
    current["user"] = users[1]
    assert client.get("/api/v2/me/passes").json()["items"][0]["is_active"] is False
    rows = client.get("/api/v2/me/receipts").json()["items"]
    assert len(rows) == 2 and {row["method"] for row in rows} == {"demo"}


def test_manual_order_uses_actual_staff_ledger_and_demo_cannot_be_collected_as_cash(portal):
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json={**body, "payment_mode": "manual"}).json()
    assert "demo_token" not in order
    current["user"] = users[0]
    result = client.post(f"/api/v2/portal/admin/orders/{order['id']}/collect", json={"payment_method": "cash", "confirmed": True})
    assert result.status_code == 200, result.text
    receipt = db.get(Payment, result.json()["receipt_id"])
    assert receipt.method == "cash" and receipt.collected_by_id == users[0].id
    current["user"] = users[1]
    order2 = client.post("/api/v2/me/orders", json={**body, "idempotency_key": "purchase-0002"}).json()
    assert order2["start_date"] > order["end_date"]
    current["user"] = users[0]
    assert client.post(f"/api/v2/portal/admin/orders/{order2['id']}/collect", json={"payment_method": "cash", "confirmed": True}).status_code == 409


def test_historical_session_grant_does_not_follow_a_vehicle_to_new_owner(portal, price_config):
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    from core.clock import business_now
    vehicle = db.get(Vehicle, body["vehicle_id"])
    session = ParkingSession(vehicle_id=vehicle.id, check_in_time=business_now(), status="active", staff_in_id=users[0].id)
    db.add(session)
    db.flush()
    capture_session_ownership(db, session)
    db.commit()
    assert len(client.get("/api/v2/me/sessions").json()["items"]) == 1
    current["user"] = users[2]
    customer2 = client.post("/api/v2/me/profile", json={"full_name": "Chủ mới", "phone_number": "0901112222"}).json()["customer"]
    vehicle.customer_id = customer2["id"]
    db.commit()
    assert client.get("/api/v2/me/sessions").json()["items"] == []
    request = client.post("/api/v2/me/vehicle-requests", json={"license_plate": vehicle.license_plate, "vehicle_type_id": kind.id}).json()
    current["user"] = users[0]
    assert client.post(f"/api/v2/portal/admin/vehicle-requests/{request['id']}/resolve", json={"approve": True}).status_code == 200
    current["user"] = users[2]
    assert len(client.get("/api/v2/me/vehicles").json()["items"]) == 1
    assert client.get("/api/v2/me/sessions").json()["items"] == []
    current["user"] = users[1]
    assert len(client.get("/api/v2/me/sessions").json()["items"]) == 1
    assert client.get("/api/v2/me/vehicles").json()["items"] == []


def test_accepted_demo_event_survives_fulfillment_crash_and_worker_retries_once(portal, monkeypatch):
    from expansion.portal_worker import run_portal_maintenance
    from expansion import portal_service
    from expansion.portal_models import PortalPaymentEvent
    from core.clock import business_now
    client, *_, db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    original = portal_service.PaymentService.record_receipt
    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated database failure after period flush")
    monkeypatch.setattr(portal_service.PaymentService, "record_receipt", interrupted)
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert result.status_code == 503
    assert client.get("/api/v2/me/passes").json()["items"] == []
    assert client.get("/api/v2/me/receipts").json()["items"] == []
    event = db.scalar(select(PortalPaymentEvent).where(PortalPaymentEvent.order_id == order["id"]))
    assert event.status == "received"
    event.next_attempt_at = business_now() - timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(portal_service.PaymentService, "record_receipt", original)
    assert run_portal_maintenance(db)["processed"] == 1
    assert run_portal_maintenance(db)["processed"] == 0
    assert client.get(f"/api/v2/me/orders/{order['id']}").json()["status"] == "fulfilled"
    assert len(client.get("/api/v2/me/passes").json()["items"]) == 1


def test_frozen_price_and_period_survive_plan_changes_and_reject_second_pending_order(portal):
    from expansion.portal_models import SubscriptionPlan
    client, *_, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    plan = db.get(SubscriptionPlan, body["plan_id"])
    plan.price, plan.duration_days = 800000, 90
    db.commit()
    replay = client.post("/api/v2/me/orders", json=body).json()
    assert replay["amount"] == 300000 and replay["end_date"] == order["end_date"]
    assert client.post("/api/v2/me/orders", json={**body, "idempotency_key": "second-pending"}).status_code == 409
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert result.json()["status"] == "fulfilled"
    assert client.get("/api/v2/me/passes").json()["items"][0]["price"] == 300000


def test_expired_order_can_be_closed_by_owner_and_worker_is_idempotent(portal):
    from expansion.portal_worker import run_portal_maintenance
    client, *_, db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    db.get(PortalOrder, order["id"]).expires_at -= timedelta(hours=1)
    db.commit()
    assert run_portal_maintenance(db)["expired"] == 1
    assert run_portal_maintenance(db)["expired"] == 0
    assert client.get(f"/api/v2/me/orders/{order['id']}").json()["status"] == "expired"


def test_due_manual_order_expires_lazily_and_no_longer_blocks_a_new_order(portal):
    client, *_unused, db = portal
    body = onboard(portal)
    first = client.post("/api/v2/me/orders", json={**body, "payment_mode": "manual"}).json()
    db.get(PortalOrder, first["id"]).expires_at -= timedelta(hours=1)
    db.commit()

    detail = client.get(f"/api/v2/me/orders/{first['id']}")
    second = client.post("/api/v2/me/orders", json={
        **body,
        "payment_mode": "manual",
        "idempotency_key": "manual-after-expiry",
    })

    assert detail.status_code == 200 and detail.json()["status"] == "expired"
    assert second.status_code == 200 and second.json()["status"] == "pending"


def test_customer_receipt_download_checks_ownership_and_labels_demo(portal):
    client, current, users, *_ = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    result = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"}).json()
    url = f"/api/v2/me/receipts/{result['receipt_id']}/pdf"
    pdf = client.get(url)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "DEMO" in pdf.headers["content-disposition"]
    current["user"] = users[2]
    client.post("/api/v2/me/profile", json={"full_name": "B", "phone_number": "0904444444"})
    assert client.get(url).status_code == 404


def test_manual_confirmation_must_be_boolean_true(portal):
    client, current, users, *_ = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json={**body, "payment_mode": "manual"}).json()
    current["user"] = users[0]
    for invalid in [False, 1, "true", None]:
        result = client.post(f"/api/v2/portal/admin/orders/{order['id']}/collect", json={"payment_method": "cash", "confirmed": invalid})
        assert result.status_code == 422


def test_manager_can_stop_plan_sales_without_rewriting_existing_order(portal):
    client, current, users, *_ = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    current["user"] = users[0]
    changed = client.patch(f"/api/v2/portal/admin/plans/{body['plan_id']}", json={"price": 600000, "is_active": False})
    assert changed.status_code == 200
    assert client.get("/api/v2/portal/admin/plans").json()["items"][0]["is_active"] is False
    assert client.get("/api/v2/portal/admin/orders").json()["items"][0]["customer_name"] == "Khách A"
    current["user"] = users[1]
    assert client.get("/api/v2/plans").json()["items"] == []
    assert client.get(f"/api/v2/me/orders/{order['id']}").json()["amount"] == 300000


def test_scoped_manager_cannot_collect_or_review_another_site_order(portal):
    from expansion.site_models import SiteMembership
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json={**body, "payment_mode": "manual"}).json()
    role = Role(name="manager")
    db.add(role)
    db.flush()
    actor = User(username="other-site-manager", full_name="Manager", role_id=role.id, password_hash="unused", is_active=True)
    other_site = ParkingSite(name="Other")
    db.add_all([actor, other_site])
    db.flush()
    db.add(SiteMembership(site_id=other_site.id, user_id=actor.id, role="manager"))
    db.commit()
    current["user"] = actor
    assert client.get("/api/v2/portal/admin/orders").json()["items"] == []
    assert client.get("/api/v2/portal/admin/plans").json()["items"] == []
    assert client.patch(f"/api/v2/portal/admin/plans/{body['plan_id']}", json={"price": 1000}).status_code == 403
    assert client.post(f"/api/v2/portal/admin/orders/{order['id']}/collect", json={"payment_method": "cash", "confirmed": True}).status_code == 403


def test_existing_customer_phone_needs_manager_approval_not_user_claim(portal):
    client, current, users, site, kind, db = portal
    original = Customer(full_name="Existing customer", phone_number="0919999999")
    db.add(original)
    db.commit()
    request = client.post("/api/v2/me/link-requests", json={"phone_number": "0919999999", "note": "Đối chiếu giấy tờ tại bãi"}).json()
    assert client.get("/api/v2/me/profile").json()["linked"] is False
    current["user"] = users[0]
    result = client.post(f"/api/v2/portal/admin/link-requests/{request['id']}/resolve", json={"approve": True})
    assert result.status_code == 200
    current["user"] = users[1]
    assert client.get("/api/v2/me/profile").json()["customer"]["id"] == original.id
    current["user"] = users[2]
    duplicate = client.post("/api/v2/me/link-requests", json={"phone_number": "0919999999"}).json()
    current["user"] = users[0]
    assert client.post(f"/api/v2/portal/admin/link-requests/{duplicate['id']}/resolve", json={"approve": True}).status_code == 409


def test_review_result_requires_explicit_manager_reason_and_can_be_cancelled(portal):
    client, current, users, site, kind, db = portal
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    db.get(PortalOrder, order["id"]).expires_at -= timedelta(hours=1)
    db.commit()
    client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    current["user"] = users[0]
    url = f"/api/v2/portal/admin/orders/{order['id']}/review"
    assert client.post(url, json={"approve": False}).status_code == 422
    assert client.post(url, json={"approve": False, "note": "Hủy mô phỏng đến muộn"}).json()["status"] == "cancelled"
    current["user"] = users[1]
    assert client.get("/api/v2/me/passes").json()["items"] == []


def test_disabled_demo_cannot_create_order_or_confirm_pending_order(portal, monkeypatch):
    client, *_, db = portal
    body = onboard(portal)
    order = client.post("/api/v2/me/orders", json=body).json()
    monkeypatch.setattr("expansion.gateway.PortalSettings", lambda: PortalSettings(_env_file=None, DEMO_PAYMENTS_ENABLED=False))
    assert client.post("/api/v2/me/orders", json={**body, "idempotency_key": "disabled-order"}).status_code == 503
    assert client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"}).status_code == 503
    assert client.get("/api/v2/me/receipts").json()["items"] == []


def test_vehicle_claim_does_not_reassign_current_owner(portal):
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    current["user"] = users[2]
    client.post("/api/v2/me/profile", json={"full_name": "B", "phone_number": "0904444444"})
    request = client.post("/api/v2/me/vehicle-requests", json={"license_plate": "30A-12345", "vehicle_type_id": kind.id}).json()
    current["user"] = users[0]
    assert client.post(f"/api/v2/portal/admin/vehicle-requests/{request['id']}/resolve", json={"approve": True}).status_code == 409
    current["user"] = users[2]
    assert client.get("/api/v2/me/vehicles").json()["items"] == []


def test_notification_read_does_not_allow_cross_customer_access(portal):
    client, current, users, *_ = portal
    onboard(portal)
    notification = client.get("/api/v2/me/notifications").json()["items"][0]
    assert notification["is_read"] is False
    assert client.post(f"/api/v2/me/notifications/{notification['id']}/read").status_code == 200
    current["user"] = users[2]
    client.post("/api/v2/me/profile", json={"full_name": "B", "phone_number": "0904444444"})
    assert client.post(f"/api/v2/me/notifications/{notification['id']}/read").status_code == 404


def test_old_session_before_vehicle_approval_does_not_receive_history_grant(portal, price_config):
    from core.clock import business_now
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    session = ParkingSession(vehicle_id=body["vehicle_id"], check_in_time=business_now() - timedelta(hours=1),
        status="active", staff_in_id=users[0].id)
    db.add(session)
    db.flush()
    capture_session_ownership(db, session)
    db.commit()
    assert client.get("/api/v2/me/sessions").json()["items"] == []
