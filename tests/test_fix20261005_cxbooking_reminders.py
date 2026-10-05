from datetime import datetime, timedelta

from sqlalchemy import select

from test_portal_api import portal, onboard  # noqa: F401  (fixture reuse)
from core.clock import business_now
from expansion.portal_models import PortalAccountLink, PortalNotification
from expansion.portal_worker import run_portal_maintenance
from models.monthly_pass import MonthlyPass


def _shift_clock(monkeypatch, days):
    import core.clock as clock
    real = datetime.now(clock.BUSINESS_TZ)
    instant = real + timedelta(days=days)

    class Shifted(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.astimezone().replace(tzinfo=None)

    monkeypatch.setattr(clock, "datetime", Shifted)


def _pay(client, order):
    res = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json={"token": order["demo_token"], "outcome": "success"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "fulfilled", res.json()
    return res.json()


def test_A_existing_pass_then_portal_renewal_still_gets_7_day_reminder(portal):
    body = onboard(portal)
    client, current, users, site, kind, db = portal
    link = db.scalar(select(PortalAccountLink).where(PortalAccountLink.user_id == users[1].id))
    today = business_now().date()
    p1 = MonthlyPass(customer_id=link.customer_id, vehicle_id=body["vehicle_id"], price=0,
        start_date=today - timedelta(days=22), end_date=today + timedelta(days=7), is_active=True)
    db.add(p1); db.commit()
    order = client.post("/api/v2/me/orders", json=body)
    assert order.status_code == 200, order.text
    order = order.json()
    print("\nRENEWAL ORDER", order["start_date"], order["end_date"])
    _pay(client, order)
    print("PASSES", [(p["id"], p["start_date"], p["end_date"], p["is_active"]) for p in client.get("/api/v2/me/passes").json()["items"]])
    result = run_portal_maintenance(db)
    print("CYCLE", result)
    for n in db.scalars(select(PortalNotification).order_by(PortalNotification.event_key)):
        print("NOTIFY", n.event_key, n.message)
    api_notes = client.get("/api/v2/me/notifications").json()["items"]
    print("API /me/notifications", [n["message"] for n in api_notes])
    assert result["reminders"] == 0
    assert not any(f"Kỳ vé #{p1.id} còn 7 ngày" in n["message"] for n in api_notes)
    # Following the reminder: a further order is accepted and sells a 3rd period.
    order2 = client.post("/api/v2/me/orders", json={**body, "idempotency_key": "purchase-0002"})
    print("FOLLOW-UP ORDER", order2.status_code, order2.json().get("start_date"), order2.json().get("end_date"), order2.json().get("amount"))
    assert order2.status_code == 200


def test_B_fully_portal_purchase_and_renewal_then_clock_advance(portal, monkeypatch):
    body = onboard(portal)
    client, current, users, site, kind, db = portal
    first = client.post("/api/v2/me/orders", json=body).json()
    _pay(client, first)
    second = client.post("/api/v2/me/orders", json={**body, "idempotency_key": "purchase-0002"}).json()
    print("\nFIRST", first["start_date"], first["end_date"], "SECOND", second["start_date"], second["end_date"])
    _pay(client, second)
    passes = client.get("/api/v2/me/passes").json()["items"]
    print("PASSES", [(p["id"], p["start_date"], p["end_date"], p["is_active"]) for p in passes])
    # Day 22: period #1 (today..today+29) has end_date == now+7, already renewed by #2.
    _shift_clock(monkeypatch, 22)
    print("NOW(+22)", business_now().date())
    r7 = run_portal_maintenance(db)
    print("CYCLE day+22", r7)
    # Day 28: end_date == now+1
    _shift_clock(monkeypatch, 28)
    print("NOW(+28)", business_now().date())
    r1 = run_portal_maintenance(db)
    print("CYCLE day+28", r1)
    rows = list(db.scalars(select(PortalNotification).where(PortalNotification.event_key.like("pass:%")).order_by(PortalNotification.event_key)))
    for n in rows:
        print("NOTIFY", n.event_key, n.message)
    assert r7["reminders"] == 0 and r1["reminders"] == 0
    assert rows == []


def test_C_control_no_reminder_when_no_period_ends_on_target(portal):
    """Control: the new pass #2 (ends far in future) on its own triggers nothing."""
    body = onboard(portal)
    client, current, users, site, kind, db = portal
    first = client.post("/api/v2/me/orders", json=body).json()
    _pay(client, first)
    result = run_portal_maintenance(db)
    print("\nCONTROL CYCLE", result)
    assert result["reminders"] == 0
