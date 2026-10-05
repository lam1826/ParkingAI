"""CL-ONLINE fixes 05/10: payment deadlines are honoured and shown (#25, #28).

Offline only: fake payOS credentials and an httpx MockTransport.
"""
from datetime import datetime

from sqlalchemy import func, select

from expansion.online_payment_models import OnlinePaymentProcessing
from expansion.online_payment_worker import run_online_payment_maintenance
from expansion.portal_models import PortalOrder
from expansion.portal_worker import run_portal_maintenance
from models.monthly_pass import MonthlyPass
from models.payment import Payment

from test_online_payments import online, no_external_payment_configuration, order_and_link, accept  # noqa: F401
from test_portal_api import portal, onboard, advance_past_order_deadline  # noqa: F401


def _counts(db):
    return (db.scalar(select(func.count()).select_from(Payment)),
            db.scalar(select(func.count()).select_from(MonthlyPass)))


# --- #28 -----------------------------------------------------------------

def test_on_time_monthly_payment_processed_after_expiry_issues_the_pass(online, monkeypatch):
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    event = accept(online)  # signed webhook committed before expires_at
    assert event.received_at < online.db.get(PortalOrder, identity).expires_at
    advance_past_order_deadline(monkeypatch, online.db, identity)
    run_online_payment_maintenance(online.db, online.config, online.gateway)
    online.db.expire_all()
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "processed"
    assert online.db.get(PortalOrder, identity).status == "fulfilled"
    assert _counts(online.db) == (1, 1)


def test_on_time_monthly_payment_survives_portal_maintenance_expiry(online, monkeypatch):
    identity, _ = order_and_link(online)
    online.state["paid"] = True
    event = accept(online)
    advance_past_order_deadline(monkeypatch, online.db, identity)
    run_portal_maintenance(online.db)
    run_online_payment_maintenance(online.db, online.config, online.gateway)
    online.db.expire_all()
    assert online.db.get(OnlinePaymentProcessing, event.id).status == "processed"
    assert online.db.get(PortalOrder, identity).status == "fulfilled"
    assert _counts(online.db) == (1, 1)


def test_on_time_monthly_payment_waits_for_lagging_provider_projection(online, monkeypatch):
    identity, _ = order_and_link(online)
    event = accept(online)  # on time; provider GET still PENDING
    advance_past_order_deadline(monkeypatch, online.db, identity)
    online.state["status"] = "PENDING"
    run_online_payment_maintenance(online.db, online.config, online.gateway)
    processing = online.db.get(OnlinePaymentProcessing, event.id)
    assert processing.status == "received" and processing.reason == "provider_settlement_pending"
    assert online.db.get(PortalOrder, identity).status in {"pending", "expired"}


def test_lazy_expiry_keeps_monthly_order_open_while_on_time_money_waits(online, monkeypatch):
    identity, _ = order_and_link(online)
    accept(online)
    advance_past_order_deadline(monkeypatch, online.db, identity)
    online.current["user"] = online.users[1]
    response = online.client.get(f"/api/v2/me/orders/{identity}")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"


def test_payment_received_after_deadline_still_goes_to_review(online, monkeypatch):
    identity, _ = order_and_link(online)
    advance_past_order_deadline(monkeypatch, online.db, identity)
    online.state["paid"] = True
    event = accept(online)
    run_online_payment_maintenance(online.db, online.config, online.gateway)
    assert online.db.get(OnlinePaymentProcessing, event.id).reason == "late_or_closed_order"
    assert _counts(online.db) == (0, 0)


# --- #25 -----------------------------------------------------------------

def _aware(value):
    return datetime.fromisoformat(value)


def test_manual_monthly_order_exposes_its_payment_deadline(portal, monkeypatch):
    client, current, users, site, kind, db = portal
    body = onboard(portal)
    plans = client.get("/api/v2/plans").json()["items"]
    monthly = next(plan for plan in plans if plan["id"] == body["plan_id"])
    assert monthly["payment_window_minutes"] == 15
    created = client.post("/api/v2/me/orders", json={**body, "payment_mode": "manual"})
    assert created.status_code == 200, created.text
    order = created.json()
    stored = db.get(PortalOrder, order["id"])
    assert order["payment_deadline"] is not None
    assert _aware(order["payment_deadline"]).replace(tzinfo=None) == stored.expires_at
    detail = client.get(f"/api/v2/me/orders/{order['id']}").json()
    assert detail["payment_deadline"] == order["payment_deadline"]
    current["user"] = users[0]
    admin_row = next(row for row in client.get("/api/v2/portal/admin/orders").json()["items"] if row["id"] == order["id"])
    assert admin_row["payment_deadline"] == order["payment_deadline"]
