"""Fleet report: narrowed session DTO, whole-set totals and stable pagination (no provider/network)."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from crud import parking_session as session_crud
from database import get_db
from expansion.site_models import FleetVehicle, Organization, OrganizationMembership, ParkingSite, SiteMembership
from expansion.site_router import router
from expansion.site_service import fleet_summary
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.role import Role
from models.user import User
from models.zone import Zone
from services.auth_service import get_current_user

SESSION_KEYS = {"id", "vehicle_id", "license_plate", "slot_name", "check_in_time", "check_out_time", "status", "parking_fee"}
FORBIDDEN_KEYS = {"staff_in_id", "staff_out_id", "monthly_pass_id", "monthly_coverage_end", "checkout_quote_hash",
                  "checkout_payment_method", "quote_hash", "image_in_url", "image_out_url", "created_at", "updated_at",
                  "parking_slot_id"}


@pytest.fixture
def env(db_session, test_user, vehicle_type, parking_slot, vehicle, customer, price_config,
        business_reference_now, monkeypatch):
    now = business_reference_now.replace(microsecond=0)
    monkeypatch.setattr(session_crud, "server_now", lambda: now)
    a, b = ParkingSite(name="Bãi A"), ParkingSite(name="Bãi B")
    db_session.add_all([a, b])
    db_session.flush()
    parking_slot.zone.site_id = a.id
    vehicle.customer_id = customer.id
    customer_role = Role(name="customer")
    db_session.add_all([customer_role, SiteMembership(site_id=a.id, user_id=test_user.id, role="manager")])
    db_session.flush()
    account = User(username="fleet-member", role_id=customer_role.id, full_name="Thành viên", password_hash="unused")
    stranger = User(username="fleet-stranger", role_id=customer_role.id, full_name="Khách khác", password_hash="unused")
    foreign_staff = User(username="fleet-foreign-staff", role_id=test_user.role_id, full_name="NV bãi B", password_hash="unused")
    org = Organization(site_id=a.id, name="Đội xe")
    db_session.add_all([account, stranger, foreign_staff, org])
    db_session.flush()
    joined_at = now - timedelta(hours=1)
    db_session.add_all([SiteMembership(site_id=b.id, user_id=foreign_staff.id, role="manager"),
                        OrganizationMembership(organization_id=org.id, user_id=account.id),
                        FleetVehicle(organization_id=org.id, vehicle_id=vehicle.id, created_at=joined_at)])
    db_session.commit()
    actor = {"user": test_user}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    return SimpleNamespace(db=db_session, staff=test_user, account=account, stranger=stranger, foreign_staff=foreign_staff,
                           a=a, b=b, org=org, slot=parking_slot, vehicle=vehicle, joined_at=joined_at,
                           actor=actor, client=TestClient(app), now=now)


def add_session(env, *, check_in, slot=None, fee=None, active=False):
    """Rows are inserted directly; completed rows carry the closing columns the DB state guard requires."""
    row = ParkingSession(vehicle_id=env.vehicle.id, parking_slot_id=(slot or env.slot).id, check_in_time=check_in,
                         status="active" if active else "completed", staff_in_id=env.staff.id,
                         check_out_time=None if active else check_in + timedelta(minutes=30),
                         parking_fee=None if active else fee, staff_out_id=None if active else env.staff.id)
    env.db.add(row)
    env.db.commit()
    return row


def test_session_entries_expose_only_reporting_fields(env):
    add_session(env, check_in=env.now - timedelta(minutes=30), fee=25_000)
    add_session(env, check_in=env.now - timedelta(minutes=5), active=True)
    env.actor["user"] = env.account
    response = env.client.get(f"/api/v2/organizations/{env.org.id}/fleet")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["sessions"]) == 2
    for entry in body["sessions"]:
        assert set(entry) == SESSION_KEYS
        assert not FORBIDDEN_KEYS & set(entry)
        assert entry["license_plate"] == env.vehicle.license_plate and entry["slot_name"] == env.slot.slot_name
        assert entry["check_in_time"].endswith("+07:00")
    assert body["sessions"][0]["status"] == "active" and body["sessions"][0]["parking_fee"] is None
    assert body["sessions"][1]["status"] == "completed" and body["sessions"][1]["parking_fee"] == 25_000
    assert body["sessions"][1]["check_out_time"].endswith("+07:00")
    assert body["limit"] == 50 and body["offset"] == 0 and body["total_sessions"] == 2
    assert "vé tháng" in body["fee_note"]
    for forbidden in ("staff_in_id", "monthly_pass_id", "checkout_quote_hash", "quote_hash", "password"):
        assert forbidden not in response.text


def test_totals_cover_whole_authorized_set_while_page_is_smaller(env):
    fees = [10_000, 20_000, 30_000, 40_000, 50_000, 60_000]
    for index, fee in enumerate(fees):
        add_session(env, check_in=env.now - timedelta(minutes=50 - index * 5), fee=fee)
    add_session(env, check_in=env.now - timedelta(minutes=1), active=True)
    summary = fleet_summary(env.db, env.account, env.org.id, limit=3)
    assert len(summary["sessions"]) == 3
    assert summary["total_sessions"] == 7 and summary["active_sessions"] == 1 and summary["completed_sessions"] == 6
    assert summary["parking_fees"] == sum(fees)
    assert summary["limit"] == 3 and summary["offset"] == 0
    # Newest first, and the second page continues where the first stopped.
    times = [row["check_in_time"] for row in summary["sessions"]]
    assert times == sorted(times, reverse=True)
    assert summary["sessions"][0]["status"] == "active"
    second = fleet_summary(env.db, env.account, env.org.id, limit=3, offset=3)
    assert len(second["sessions"]) == 3 and second["total_sessions"] == 7 and second["parking_fees"] == sum(fees)
    assert {row["id"] for row in summary["sessions"]}.isdisjoint(row["id"] for row in second["sessions"])
    last = fleet_summary(env.db, env.account, env.org.id, limit=3, offset=6)
    assert len(last["sessions"]) == 1 and last["sessions"][0]["parking_fee"] == 10_000
    assert fleet_summary(env.db, env.account, env.org.id, limit=3, offset=7)["sessions"] == []


def test_ordering_breaks_check_in_ties_by_id_descending(env):
    same = env.now - timedelta(minutes=10)
    rows = [add_session(env, check_in=same, fee=fee) for fee in (1_000, 2_000, 3_000)]
    listed = [row["id"] for row in fleet_summary(env.db, env.account, env.org.id)["sessions"]]
    assert listed == sorted((row.id for row in rows), reverse=True)


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_page_bounds_are_enforced(env, kwargs):
    with pytest.raises(HTTPException) as exc:
        fleet_summary(env.db, env.account, env.org.id, **kwargs)
    assert exc.value.status_code == 422


def test_pre_join_and_foreign_site_sessions_are_excluded_from_list_and_totals(env):
    add_session(env, check_in=env.joined_at - timedelta(minutes=1), fee=99_000)
    zone_b = Zone(site_id=env.b.id, name="Bãi B - Khu 1", capacity=5)
    env.db.add(zone_b)
    env.db.flush()
    slot_b = ParkingSlot(zone_id=zone_b.id, vehicle_type_id=env.vehicle.vehicle_type_id, slot_name="B-01")
    env.db.add(slot_b)
    env.db.commit()
    add_session(env, check_in=env.now - timedelta(minutes=20), slot=slot_b, fee=77_000)
    visible = add_session(env, check_in=env.now - timedelta(minutes=10), fee=15_000)
    summary = fleet_summary(env.db, env.account, env.org.id)
    assert [row["id"] for row in summary["sessions"]] == [visible.id]
    assert summary["total_sessions"] == 1 and summary["completed_sessions"] == 1 and summary["active_sessions"] == 0
    assert summary["parking_fees"] == 15_000


def test_non_member_customer_and_foreign_site_staff_get_403(env):
    add_session(env, check_in=env.now - timedelta(minutes=10), fee=15_000)
    path = f"/api/v2/organizations/{env.org.id}/fleet"
    assert env.client.get(path).status_code == 200
    env.actor["user"] = env.account
    assert env.client.get(path).status_code == 200
    env.actor["user"] = env.stranger
    assert env.client.get(path).status_code == 403
    env.actor["user"] = env.foreign_staff
    assert env.client.get(path).status_code == 403
