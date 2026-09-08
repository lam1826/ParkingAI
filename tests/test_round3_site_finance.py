"""HTTP contract for finance on multi-site installations, using disposable SQLite."""
from datetime import timedelta

from sqlalchemy import select

from test_expansion_sites import env  # noqa: F401
from models.payment import Payment
from models.cash_shift import CashShift
from services.parking_service import ParkingService
from models.role import Role


def test_admin_cannot_open_new_unscoped_shift_when_multiple_sites_exist(env):
    from fastapi import Depends
    from routers.cash_shift import router as cash_router
    from expansion.system_router import require_legacy_workspace
    env.client.app.include_router(cash_router, prefix="/api/v1/cash-shifts", dependencies=[Depends(require_legacy_workspace)])
    role = env.db.scalar(select(Role).where(Role.name == "admin"))
    if role is None:
        role = Role(name="admin"); env.db.add(role); env.db.flush()
    env.staff.role = role
    env.db.commit()
    response = env.client.post("/api/v1/cash-shifts", json={"opening_cash": 0})
    assert response.status_code == 409, response.text
    assert env.db.scalars(select(CashShift)).all() == []
    scoped = env.client.post(f"/api/v2/sites/{env.a.id}/cash-shifts", json={"opening_cash": 0})
    assert scoped.status_code == 201 and scoped.json()["site_id"] == env.a.id


def test_scoped_shift_open_close_and_foreign_site_denial(env):
    root = f"/api/v2/sites/{env.a.id}"
    opened = env.client.post(root + "/cash-shifts", json={"opening_cash": 100000})
    assert opened.status_code == 201, opened.text
    row = opened.json()
    assert row["site_id"] == env.a.id
    assert env.client.get(f"/api/v2/sites/{env.b.id}/cash-shifts").status_code == 403
    assert env.client.post(root + "/cash-shifts", json={"opening_cash": 0}).status_code == 409
    closed = env.client.post(root + f"/cash-shifts/{row['id']}/close", json={"counted_cash": 100000})
    assert closed.status_code == 200, closed.text
    assert closed.json()["difference"] == 0
    assert env.client.post(root + f"/cash-shifts/{row['id']}/close", json={"counted_cash": 0}).status_code == 409


def test_scoped_checkout_records_site_and_own_shift(env):
    root = f"/api/v2/sites/{env.a.id}"
    response = env.client.post(root + "/cash-shifts", json={"opening_cash": 0})
    assert response.status_code == 201, response.text
    shift_id = response.json()["id"]
    session = ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id,
        env.staff.id, parking_slot_id=env.slot.id, _expected_site_id=env.a.id)
    session_id = session["session_id"]
    env.clock["now"] += timedelta(hours=1)
    quote = env.client.get(root + f"/sessions/{session_id}/checkout-quote")
    assert quote.status_code == 200, quote.text
    payload = {"quote_token": quote.json()["quote_token"], "payment_confirmed": True, "payment_method": "cash"}
    assert env.client.put(root + f"/sessions/{session_id}/check-out", json=payload).status_code == 200
    assert env.client.put(root + f"/sessions/{session_id}/check-out", json=payload).status_code == 200
    receipts = env.db.scalars(select(Payment).where(Payment.source_id == session_id)).all()
    assert len(receipts) == 1
    assert receipts[0].site_id == env.a.id and receipts[0].shift_id == shift_id
    listing = env.client.get(root + "/payments").json()
    assert listing["total"] == 1
    assert env.client.get(root + f"/payments/{receipts[0].id}/pdf").content.startswith(b"%PDF")
    assert env.client.get(root + "/revenue").json()["total_revenue"] == receipts[0].amount


def test_customer_cannot_operate_finance_or_override_site(env):
    root = f"/api/v2/sites/{env.a.id}"
    assert env.client.post(root + "/cash-shifts", json={"opening_cash": 0, "site_id": env.b.id}).status_code == 422
    env.actor["user"] = env.account
    assert env.client.get(root + "/payments").status_code == 403
    assert env.client.post(root + "/cash-shifts", json={"opening_cash": 0}).status_code == 403
    assert env.db.scalars(select(CashShift)).all() == []


def test_scoped_edit_reuses_zone_and_slot_guards(env):
    root = f"/api/v2/sites/{env.a.id}"
    changed = env.client.patch(root + f"/zones/{env.slot.zone_id}", json={"name": "Khu A updated"})
    assert changed.status_code == 200, changed.text
    assert env.client.patch(root + f"/slots/{env.slot.id}", json={"slot_name": "A-REVISED"}).status_code == 200
    assert env.client.patch(f"/api/v2/sites/{env.b.id}/slots/{env.slot.id}", json={"is_active": False}).status_code == 403


def test_global_role_downgrade_revokes_manager_operations_with_stale_site_grant(env):
    root = f"/api/v2/sites/{env.a.id}"
    assert env.staff.role.name == "manager"
    assert env.client.patch(root + f"/zones/{env.slot.zone_id}", json={"name": "Allowed before downgrade"}).status_code == 200
    role = env.db.scalar(select(Role).where(Role.name == "staff"))
    if role is None:
        role = Role(name="staff"); env.db.add(role); env.db.flush()
    env.staff.role = role
    env.db.commit()
    assert env.client.patch(root + f"/zones/{env.slot.zone_id}", json={"name": "Unauthorized rename"}).status_code == 403
    assert env.client.get("/api/v2/sites").json()[0]["role"] == "staff"
    assert env.client.get(root + "/sessions").status_code == 200
