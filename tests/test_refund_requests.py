"""Receipt-based refund requests: DEMO, counter and online money; server-side amounts; races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from expansion import refund_service
from expansion.portal_models import PortalNotification, PortalOrder
from expansion.support_models import PaymentRefundRequest
from expansion.support_router import router as support_router
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.user import User
from test_online_payments import no_external_payment_configuration, online  # noqa: F401
from test_portal_api import onboard, portal  # noqa: F401
from test_session_online_payments import checkout, link, parking_online, quote, settle  # noqa: F401


def _app(portal):
    client, current, users, site, kind, db = portal
    client.app.include_router(support_router, prefix="/api/v2")
    return client, current, users, site, db


def _paid_demo_order(portal):
    client = portal[0]
    order = client.post("/api/v2/me/orders", json=onboard(portal)).json()
    paid = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert paid.status_code == 200, paid.text
    return paid.json()


def _collected_manual_order(portal, key="purchase-manual"):
    client, current, users, site, kind, db = portal
    body = {**onboard(portal), "payment_mode": "manual", "idempotency_key": key}
    order = client.post("/api/v2/me/orders", json=body).json()
    current["user"] = users[0]
    collected = client.post(f"/api/v2/portal/admin/orders/{order['id']}/collect", json={"payment_method": "cash", "confirmed": True})
    assert collected.status_code == 200, collected.text
    current["user"] = users[1]
    return collected.json()


def _receipt_row(client, receipt_id):
    return next(row for row in client.get("/api/v2/me/receipts").json()["items"] if row["id"] == receipt_id)


def test_demo_receipt_refund_is_server_priced_idempotent_and_settled_at_approval(portal):
    client, current, users, site, db = _app(portal)
    order = _paid_demo_order(portal)
    row = _receipt_row(client, order["receipt_id"])
    assert row["refund"]["eligible"] is True and row["refund"]["refundable_amount"] == 300000
    assert row["refund"]["payment_channel"] == "demo" and row["refund"]["refunded_amount"] == 0
    # The client never sends an amount; a forged amount is rejected by the schema.
    assert client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "x", "amount": 1}).status_code == 422
    created = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Không dùng nữa"})
    assert created.status_code == 201, created.text
    request = created.json()
    assert request["status"] == "pending" and request["requested_amount"] == 300000 and request["demo"] is True
    assert request["order_id"] == order["id"]
    replay = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "lại"})
    assert replay.status_code == 201 and replay.json()["id"] == request["id"]
    assert _receipt_row(client, order["receipt_id"])["refund"]["blocked_reason"] == "request_open"
    mine = client.get("/api/v2/me/refund-requests").json()["items"]
    assert mine[0]["id"] == request["id"] and mine[0]["status_label"] == "Đã tiếp nhận"
    # Only a manager of the site decides; the customer cannot approve their own request.
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    assert client.post(url + "/approve", json={}).status_code == 403
    current["user"] = users[0]
    detail = client.get(url).json()
    assert detail["refund_state"]["refundable_amount"] == 300000 and detail["receipt"]["method"] == "demo"
    assert client.post(url + "/approve", json={"amount": 300001}).status_code == 409
    approved = client.post(url + "/approve", json={"note": "Đã kiểm tra"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "refunded" and approved.json()["refund_method"] == "demo"
    again = client.post(url + "/approve", json={"note": "Đã kiểm tra"})
    assert again.json()["refund_payment_id"] == approved.json()["refund_payment_id"]
    assert client.post(url + "/record-refund", json={"method": "cash", "confirmed": True}).status_code == 409
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is False
    assert db.get(PortalOrder, order["id"]).status == "refunded"
    current["user"] = users[1]
    rows = client.get("/api/v2/me/receipts").json()["items"]
    assert {row["method"] for row in rows} == {"demo"} and len(rows) == 2
    original = _receipt_row(client, order["receipt_id"])
    assert original["refund"]["eligible"] is False and original["refund"]["blocked_reason"] == "fully_refunded"
    assert db.scalar(select(PortalNotification).where(PortalNotification.event_key == f"refund:{request['id']}:refunded")) is not None


def test_counter_receipt_refund_is_approved_then_recorded_with_reference_and_never_exceeds_balance(portal):
    client, current, users, site, db = _app(portal)
    order = _collected_manual_order(portal)
    row = _receipt_row(client, order["receipt_id"])
    assert row["refund"]["payment_channel"] == "counter" and row["refund"]["refundable_amount"] == 300000
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Chuyển công tác"}).json()
    url = f"/api/v2/sites/{site.id}/refund-requests/{request['id']}"
    current["user"] = users[0]
    reviewing = client.post(url + "/review", json={"note": "Đang đối chiếu"})
    assert reviewing.json()["status"] == "reviewing"
    assert client.post(url + "/reject", json={"note": ""}).status_code == 422
    assert client.post(url + "/approve", json={"amount": 300001}).status_code == 409
    assert client.post(url + "/record-refund", json={"method": "cash", "confirmed": True}).status_code == 409  # not approved yet
    approved = client.post(url + "/approve", json={"amount": 100000, "note": "Hoàn phần chưa dùng"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved" and approved.json()["refund_payment_id"] is None
    # Approval alone moves no money: still exactly one ledger row.
    assert db.scalar(select(func.count()).select_from(Payment)) == 1
    assert client.post(url + "/record-refund", json={"method": "transfer", "confirmed": True}).status_code == 422
    assert client.post(url + "/record-refund", json={"method": "transfer", "external_reference": "FT26091600123", "confirmed": False}).status_code == 422
    recorded = client.post(url + "/record-refund", json={"method": "transfer", "external_reference": "FT26091600123", "confirmed": True})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["status"] == "refunded" and recorded.json()["external_reference"] == "FT26091600123"
    refund = db.get(Payment, recorded.json()["refund_payment_id"])
    assert refund.kind == "refund" and refund.amount == 100000 and refund.method == "transfer" and refund.original_payment_id == order["receipt_id"]
    assert refund.collected_by_id == users[0].id and "Chuyển công tác" in refund.reason
    replay = client.post(url + "/record-refund", json={"method": "transfer", "external_reference": "FT26091600123", "confirmed": True})
    assert replay.json()["refund_payment_id"] == refund.id
    assert client.post(url + "/record-refund", json={"method": "cash", "confirmed": True}).status_code == 409
    assert db.get(MonthlyPass, order["monthly_pass_id"]).is_active is False
    current["user"] = users[1]
    original = _receipt_row(client, order["receipt_id"])
    # The remaining 200.000 cannot be requested again: the entitlement is gone.
    assert original["refund"]["refunded_amount"] == 100000 and original["refund"]["blocked_reason"] == "pass_inactive"
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.kind == "refund")) == 1


def test_rejection_requires_reason_and_other_customers_or_staff_cannot_touch_requests(portal):
    client, current, users, site, db = _app(portal)
    order = _paid_demo_order(portal)
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Nhầm gói"}).json()
    current["user"] = users[2]
    assert client.post("/api/v2/me/profile", json={"full_name": "Khách B", "phone_number": "0909999999"}).status_code == 200
    assert client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "hack"}).status_code == 404
    assert client.get("/api/v2/me/refund-requests").json()["items"] == []
    assert client.get(f"/api/v2/sites/{site.id}/refund-requests").status_code == 403
    current["user"] = users[0]
    listed = client.get(f"/api/v2/sites/{site.id}/refund-requests", params={"status": "pending"}).json()["items"]
    assert [row["id"] for row in listed] == [request["id"]] and listed[0]["customer_name"] == "Khách A"
    rejected = client.post(f"/api/v2/sites/{site.id}/refund-requests/{request['id']}/reject", json={"note": "Vé đã dùng"})
    assert rejected.json()["status"] == "rejected" and rejected.json()["decision_note"] == "Vé đã dùng"
    assert client.post(f"/api/v2/sites/{site.id}/refund-requests/{request['id']}/approve", json={}).status_code == 409
    assert db.scalar(select(func.count()).select_from(Payment).where(Payment.kind == "refund")) == 0
    current["user"] = users[1]
    # A rejected request frees the receipt for a new request.
    later = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Xem lại"})
    assert later.status_code == 201 and later.json()["id"] != request["id"]
    assert [row["status"] for row in client.get("/api/v2/me/refund-requests").json()["items"]] == ["pending", "rejected"]
    assert db.scalar(select(PortalNotification).where(PortalNotification.event_key == f"refund:{request['id']}:rejected")) is not None


def test_legacy_order_route_and_admin_resolve_use_the_receipt_workflow(portal):
    client, current, users, site, db = _app(portal)
    order = _collected_manual_order(portal, key="purchase-legacy-route")
    created = client.post(f"/api/v2/me/orders/{order['id']}/refund-requests", json={"reason": "Qua màn hình đơn"})
    assert created.status_code == 200, created.text
    assert created.json()["order_id"] == order["id"] and created.json()["payment_channel"] == "counter"
    current["user"] = users[0]
    merged = client.get("/api/v2/portal/admin/refund-requests").json()["items"]
    assert merged[0]["id"] == created.json()["id"] and merged[0]["legacy"] is False
    resolved = client.post(f"/api/v2/portal/admin/refund-requests/{created.json()['id']}/resolve", json={"approve": True, "note": "ok"})
    assert resolved.status_code == 200, resolved.text
    # Counter money is not refunded by approval; the manager must record the external refund.
    assert resolved.json()["status"] == "approved" and resolved.json()["refund_payment_id"] is None


def test_applied_online_credit_is_not_refundable_and_surplus_math_is_bounded(parking_online, monkeypatch):
    ctx = parking_online
    proposal = quote(ctx)
    code = link(ctx, proposal)
    settle(ctx, code)
    ctx.client.app.include_router(support_router, prefix="/api/v2")
    credited = ctx.client.get("/api/v2/me/receipts").json()["items"]
    online = next(row for row in credited if row["source_type"] == "session_credit")
    assert online["refund"]["payment_channel"] == "online" and online["refund"]["blocked_reason"] == "session_not_completed"
    checkout(ctx)
    after = next(row for row in ctx.client.get("/api/v2/me/receipts").json()["items"] if row["id"] == online["id"])
    assert after["refund"]["eligible"] is False and after["refund"]["blocked_reason"] == "credit_applied"
    assert ctx.client.post(f"/api/v2/me/receipts/{online['id']}/refund-requests", json={"reason": "x"}).status_code == 409
    # Surplus arithmetic on a stub: credits 10.000, final fee 4.000, 2.000 already refunded => 4.000 left.
    credit = SimpleNamespace(session_id="s", receipt_id="r1", amount=10000)
    session = SimpleNamespace(status="completed", parking_fee=4000, id="s")

    class Stub:
        def get(self, model, identity):
            return session

        def scalars(self, statement):
            return [credit]

        def execute(self, statement):
            return SimpleNamespace(scalars=lambda: [2000])

    surplus, problem = refund_service._credit_surplus(Stub(), credit)
    assert (surplus, problem) == (4000, None)
    session.status = "active"
    assert refund_service._credit_surplus(Stub(), credit) == (None, "session_not_completed")


def test_concurrent_approvals_and_requests_never_double_refund(portal, tmp_path):
    client, current, users, site, db = _app(portal)
    order = _paid_demo_order(portal)
    request = client.post(f"/api/v2/me/receipts/{order['receipt_id']}/refund-requests", json={"reason": "Đồng thời"}).json()
    db.commit()
    engine = create_engine("sqlite:///" + (tmp_path / "refund-concurrent.sqlite").as_posix(),
        connect_args={"timeout": 15, "check_same_thread": False})
    source, target = db.get_bind().raw_connection(), engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    barrier = Barrier(2)
    manager_id, customer_id = users[0].id, users[1].id

    def approve():
        with factory() as session:
            actor = session.get(User, manager_id)
            barrier.wait(timeout=10)
            item = refund_service.approve(session, actor, site.id, request["id"], note="race")
            return item.refund_payment_id

    def request_again():
        with factory() as session:
            actor = session.get(User, customer_id)
            barrier.wait(timeout=10)
            return refund_service.create_request(session, actor, order["receipt_id"], "race").id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=25) for future in [pool.submit(approve) for _ in range(2)]]
        assert results[0] == results[1] is not None
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Payment).where(Payment.kind == "refund")) == 1
            assert session.scalar(select(func.count()).select_from(PaymentRefundRequest)) == 1
        # After settlement the receipt is exhausted: simultaneous new requests cannot open anything.
        barrier.reset()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request_again) for _ in range(2)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=25))
                except Exception as error:  # HTTPException 409: fully refunded
                    outcomes.append(type(error).__name__ + str(getattr(error, "status_code", "")))
        assert all(str(item).startswith("HTTPException409") for item in outcomes), outcomes
    finally:
        engine.dispose()
