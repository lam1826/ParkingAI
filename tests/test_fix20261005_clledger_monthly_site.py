"""Review 05/10/2026 #0 (P1-1): counter monthly receipts belong to the selling site.

Selling or renewing a monthly pass at the counter must work while the seller
has an open site cash shift, and the receipt must reach that site's finance
(revenue, payments list and shift reconciliation). The DB guard keeps portal
periods pinned to their order's site.
"""
import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.clock import business_now
from expansion.site_models import ParkingSite, SiteMembership
from models.cash_shift import CashShift
from models.monthly_pass import MonthlyPass
from models.payment import Payment
from models.role import Role
from models.user import User
from services.auth_service import AuthService


def _headers(user):
    token = AuthService().create_access_token(user_id=user.id, username=user.username,
        role=user.role.name, password_hash=user.password_hash)
    return {"Authorization": "Bearer " + token}


def _site(db, user, name="Only lot"):
    site = ParkingSite(name=name, is_active=True)
    db.add(site)
    db.flush()
    db.add(SiteMembership(site_id=site.id, user_id=user.id, role="manager"))
    db.commit()
    return site


def _payload(customer, vehicle, code="CARD-001", **extra):
    start = business_now().date() + datetime.timedelta(days=1)
    return {"customer_id": customer.id, "vehicle_id": vehicle.id, "pass_code": code, "price": 500000,
            "start_date": start.isoformat(), "end_date": (start + datetime.timedelta(days=30)).isoformat(),
            "payment_method": "cash", **extra}


def _admin(db):
    role = db.scalar(select(Role).where(Role.name == "admin"))
    if role is None:
        role = Role(name="admin")
        db.add(role)
        db.flush()
    user = User(username="ledger_admin", full_name="Admin", password_hash="unused", role_id=role.id, is_active=True)
    db.add(user)
    db.commit()
    return user


def test_counter_sale_with_open_shift_is_attached_to_shift_and_site(client, db_session, manager_user, customer, vehicle):
    site = _site(db_session, manager_user)
    shift = client.post("/api/v1/cash-shifts", json={"opening_cash": 0}, headers=_headers(manager_user))
    assert shift.status_code == 201, shift.text
    created = client.post("/api/v1/monthly-passes", json=_payload(customer, vehicle), headers=_headers(manager_user))
    assert created.status_code == 201, created.text
    receipt = db_session.scalar(select(Payment).where(Payment.source_type == "monthly_pass"))
    assert receipt.site_id == site.id and receipt.shift_id == shift.json()["id"]
    summary = client.get(f"/api/v2/sites/{site.id}/cash-shifts/{shift.json()['id']}", headers=_headers(manager_user)).json()
    assert summary["cash_receipts"] == 500000 and summary["expected_cash"] == 500000
    day = receipt.created_at.date().isoformat()
    revenue = client.get(f"/api/v2/sites/{site.id}/revenue", params={"date_from": day, "date_to": day},
        headers=_headers(manager_user)).json()
    assert revenue["total_revenue"] == 500000 and revenue["payment_count"] == 1
    listed = client.get(f"/api/v2/sites/{site.id}/payments", headers=_headers(manager_user)).json()
    assert [row["id"] for row in listed["items"]] == [receipt.id]


def test_counter_renewal_with_open_site_shift_succeeds(client, db_session, manager_user, customer, vehicle):
    site = _site(db_session, manager_user)
    created = client.post("/api/v1/monthly-passes", json=_payload(customer, vehicle), headers=_headers(manager_user))
    assert created.status_code == 201, created.text
    shift = client.post(f"/api/v2/sites/{site.id}/cash-shifts", json={"opening_cash": 0}, headers=_headers(manager_user))
    assert shift.status_code == 201, shift.text
    period = created.json()
    start = datetime.date.fromisoformat(period["end_date"]) + datetime.timedelta(days=1)
    body = {"start_date": start.isoformat(), "end_date": (start + datetime.timedelta(days=29)).isoformat(),
            "price": 500000, "payment_method": "cash", "request_id": "renew-request-0001"}
    renewed = client.post(f"/api/v1/monthly-passes/{period['id']}/renew", json=body, headers=_headers(manager_user))
    assert renewed.status_code == 201, renewed.text
    receipts = db_session.scalars(select(Payment).where(Payment.source_type == "monthly_pass")).all()
    assert {row.site_id for row in receipts} == {site.id}
    renewal = next(row for row in receipts if row.source_id == str(renewed.json()["id"]))
    assert renewal.shift_id == shift.json()["id"]


def test_counter_sale_without_shift_reaches_site_finance(client, db_session, manager_user, customer, vehicle):
    site = _site(db_session, manager_user)
    created = client.post("/api/v1/monthly-passes", json=_payload(customer, vehicle), headers=_headers(manager_user))
    assert created.status_code == 201, created.text
    receipt = db_session.scalar(select(Payment).where(Payment.source_type == "monthly_pass"))
    assert receipt.site_id == site.id and receipt.shift_id is None
    day = receipt.created_at.date().isoformat()
    revenue = client.get(f"/api/v2/sites/{site.id}/revenue", params={"date_from": day, "date_to": day},
        headers=_headers(manager_user)).json()
    assert revenue["total_revenue"] == 500000 and revenue["unassigned_revenue"] == 500000


def test_multi_site_counter_sale_needs_a_site_and_honours_the_shift(client, db_session, customer, vehicle):
    admin = _admin(db_session)
    first, second = _site(db_session, admin, "Lot 1"), _site(db_session, admin, "Lot 2")
    refused = client.post("/api/v1/monthly-passes", json=_payload(customer, vehicle), headers=_headers(admin))
    assert refused.status_code == 409, refused.text
    assert db_session.scalar(select(MonthlyPass.id)) is None and db_session.scalar(select(Payment.id)) is None
    chosen = client.post("/api/v1/monthly-passes", json=_payload(customer, vehicle, site_id=second.id), headers=_headers(admin))
    assert chosen.status_code == 201, chosen.text
    assert db_session.scalar(select(Payment.site_id).where(Payment.source_id == str(chosen.json()["id"]))) == second.id
    shift = client.post(f"/api/v2/sites/{first.id}/cash-shifts", json={"opening_cash": 0}, headers=_headers(admin))
    assert shift.status_code == 201, shift.text
    start = datetime.date.fromisoformat(chosen.json()["end_date"]) + datetime.timedelta(days=1)
    renewal = {"start_date": start.isoformat(), "end_date": (start + datetime.timedelta(days=29)).isoformat(),
               "price": 500000, "payment_method": "cash", "request_id": "renew-multi-site-0001"}
    # An explicit site that differs from the seller's open shift is refused.
    conflict = client.post(f"/api/v1/monthly-passes/{chosen.json()['id']}/renew", json={**renewal, "site_id": second.id},
        headers=_headers(admin))
    assert conflict.status_code == 409, conflict.text
    renewed = client.post(f"/api/v1/monthly-passes/{chosen.json()['id']}/renew", json=renewal, headers=_headers(admin))
    assert renewed.status_code == 201, renewed.text
    row = db_session.scalar(select(Payment).where(Payment.source_id == str(renewed.json()["id"])))
    assert row.site_id == first.id and row.shift_id == shift.json()["id"]


def test_requested_site_is_validated_before_any_write(client, db_session, manager_user, customer, vehicle):
    _site(db_session, manager_user)
    response = client.post("/api/v1/monthly-passes", json=_payload(customer, vehicle, site_id=999),
        headers=_headers(manager_user))
    assert response.status_code == 404, response.text
    assert db_session.scalar(select(MonthlyPass.id)) is None and db_session.scalar(select(Payment.id)) is None


def test_db_guard_keeps_portal_periods_on_their_order_site(db_session, customer, vehicle, test_user):
    from expansion.portal_models import PortalOrder, SubscriptionPlan
    first = ParkingSite(name="Lot A", is_active=True)
    second = ParkingSite(name="Lot B", is_active=True)
    db_session.add_all([first, second])
    db_session.flush()
    plan = SubscriptionPlan(name="30 ngày", site_id=first.id, vehicle_type_id=vehicle.vehicle_type_id,
        duration_days=30, price=300000)
    db_session.add(plan)
    db_session.flush()
    today = business_now().date()
    order = PortalOrder(user_id=test_user.id, customer_id=customer.id, vehicle_id=vehicle.id, plan_id=plan.id,
        site_id=first.id, amount=300000, start_date=today, end_date=today + datetime.timedelta(days=29),
        payment_mode="manual", idempotency_key="guard-order-0001", expires_at=business_now() + datetime.timedelta(minutes=15))
    db_session.add(order)
    db_session.flush()
    portal_period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=300000, start_date=today,
        end_date=today + datetime.timedelta(days=29), renewal_key=f"portal:{order.id}", pass_code="GUARD-PORTAL")
    counter_period = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, price=200000,
        start_date=today + datetime.timedelta(days=40), end_date=today + datetime.timedelta(days=69), pass_code="GUARD-COUNTER")
    db_session.add_all([portal_period, counter_period])
    db_session.commit()

    def insert(period, site_id, key):
        db_session.add(Payment(source_type="monthly_pass", source_id=str(period.id), site_id=site_id, kind="receipt",
            amount=period.price, method="cash", idempotency_key=key))
        db_session.flush()

    with pytest.raises(IntegrityError, match="payment site mismatch"):
        insert(portal_period, second.id, "guard-portal-wrong")
    db_session.rollback()
    insert(portal_period, first.id, "guard-portal-right")
    # A counter period has no order: the selling site is accepted.
    insert(counter_period, second.id, "guard-counter-site")
    db_session.commit()
    assert {row.site_id for row in db_session.scalars(select(Payment))} == {first.id, second.id}


def test_sqlite_upgrade_bridge_holds_the_exact_previous_site_guard():
    """db_rollout upgrades schema10 SQLite through the root bridge; it must carry this exact text."""
    from review_20261005_rollout import PRE_REVIEW_20261005_TRIGGER_SQL
    from site_finance_guards import PRE_REVIEW_20261005_SITE_FINANCE_SQLITE_GUARDS, SITE_FINANCE_SQLITE_GUARDS
    old = PRE_REVIEW_20261005_SITE_FINANCE_SQLITE_GUARDS["trg_payment_site_guard"]
    assert old != SITE_FINANCE_SQLITE_GUARDS["trg_payment_site_guard"]
    assert PRE_REVIEW_20261005_TRIGGER_SQL["trg_payment_site_guard"] == old
    # End-to-end upgrade coverage lives in tests/test_fix20261005_root_rollout_bridge.py.


def test_migration_freezes_the_exact_guard_definitions():
    """Migration 20261005_12 and the guard module must describe the same guard."""
    import importlib.util
    from pathlib import Path
    import site_finance_guards as guards
    path = Path(__file__).resolve().parents[1] / "backend/alembic/versions/20261005_12_review_finance_site.py"
    spec = importlib.util.spec_from_file_location("review_finance_site_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert (migration.revision, migration.down_revision) == ("20261005_12", "20261005_11")
    assert migration.SQLITE_GUARDS == {"trg_payment_site_guard": guards.SITE_FINANCE_SQLITE_GUARDS["trg_payment_site_guard"]}
    assert migration.PREVIOUS_SQLITE_GUARDS == guards.PRE_REVIEW_20261005_SITE_FINANCE_SQLITE_GUARDS

    def function(sql):
        start = sql.index("CREATE OR REPLACE FUNCTION parking_payment_site_guard")
        return " ".join(sql[start:sql.index("LANGUAGE plpgsql;", start)].split())

    assert function(migration.UPGRADE_POSTGRES_SQL) == function(guards.SITE_FINANCE_POSTGRES_SQL)
    assert "IF NOT FOUND THEN expected_site := NEW.site_id" in migration.UPGRADE_POSTGRES_SQL
    assert "IF NOT FOUND" not in migration.PREVIOUS_POSTGRES_SQL
