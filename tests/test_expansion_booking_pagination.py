"""Server-side scope/status/window filters and stable pages for bookings, allocations and waitlist."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.clock import BUSINESS_TZ
from database import get_db
from expansion.portal_models import PortalAccountLink, PortalVehicleOwnership
from expansion.site_models import GuaranteedAllocation, ParkingReservation, ParkingSite, SiteMembership, SiteWaitlist
from expansion.site_router import router
from models.customer import Customer
from models.parking_slot import ParkingSlot
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.zone import Zone
from services.auth_service import get_current_user

@pytest.fixture
def env(db_session, test_user, vehicle_type, parking_slot, vehicle, customer, business_reference_now):
    now = business_reference_now.replace(microsecond=0)
    a, b = ParkingSite(name="Bãi A"), ParkingSite(name="Bãi B")
    db_session.add_all([a, b])
    db_session.flush()
    parking_slot.zone.site_id = a.id
    zone_b = Zone(site_id=b.id, name="Khu B", capacity=5, is_active=True)
    db_session.add(zone_b)
    db_session.flush()
    slot_b = ParkingSlot(zone_id=zone_b.id, vehicle_type_id=vehicle_type.id, slot_name="B-01")
    vehicle.customer_id = customer.id
    customer2 = Customer(full_name="Khách hai", phone_number="0902000222")
    db_session.add_all([slot_b, customer2])
    db_session.flush()
    vehicle2 = Vehicle(license_plate="51C22222", vehicle_type_id=vehicle_type.id, customer_id=customer2.id)
    role = Role(name="customer")
    db_session.add_all([vehicle2, role])
    db_session.flush()
    account = User(username="pager-customer", role_id=role.id, full_name="Khách", password_hash="unused")
    other = User(username="pager-other", role_id=role.id, full_name="Khách hai", password_hash="unused")
    staff_b = User(username="pager-staff-b", role_id=test_user.role_id, full_name="NV B", password_hash="unused")
    db_session.add_all([account, other, staff_b])
    db_session.flush()
    db_session.add_all([
        SiteMembership(site_id=a.id, user_id=test_user.id, role="manager"),
        SiteMembership(site_id=b.id, user_id=staff_b.id, role="staff"),
        PortalAccountLink(user_id=account.id, customer_id=customer.id, verification="manager", verified_by_id=test_user.id),
        PortalAccountLink(user_id=other.id, customer_id=customer2.id, verification="manager", verified_by_id=test_user.id),
        PortalVehicleOwnership(customer_id=customer.id, vehicle_id=vehicle.id, approved_by_id=test_user.id, approved_at=now),
        PortalVehicleOwnership(customer_id=customer2.id, vehicle_id=vehicle2.id, approved_by_id=test_user.id, approved_at=now),
    ])
    # 130 reservations interleaved across two sites and two customers; pairs share a start_at so
    # the secondary `id` key is exercised. DB guards only accept the initial status and
    # non-overlapping windows per slot, so rows are inserted adjacent and re-statused afterwards.
    reservations, allocations, waitlist = [], [], []
    for index in range(130):
        site, slot = (a, parking_slot) if index % 2 == 0 else (b, slot_b)
        owner, car = (customer, vehicle) if index % 3 else (customer2, vehicle2)
        start = now + timedelta(hours=index // 2)
        reservations.append(ParkingReservation(id=f"res-{index:04d}", site_id=site.id, slot_id=slot.id, customer_id=owner.id,
                                               vehicle_id=car.id, start_at=start, end_at=start + timedelta(hours=1),
                                               arrival_deadline=start + timedelta(minutes=15), status="confirmed",
                                               request_id=f"req-{index:04d}", created_by_id=test_user.id))
    for index in range(15):
        site, slot = (a, parking_slot) if index % 2 == 0 else (b, slot_b)
        start = now + timedelta(days=30 + index)
        allocations.append(GuaranteedAllocation(id=f"alloc-{index:03d}", site_id=site.id, slot_id=slot.id, customer_id=customer.id,
                                                vehicle_id=vehicle.id, start_at=start, end_at=start + timedelta(hours=2),
                                                status="active", request_id=f"alloc-req-{index:03d}", created_by_id=test_user.id))
    for index in range(120):
        site = a if index % 2 == 0 else b
        owner, car = (customer, vehicle) if index % 3 else (customer2, vehicle2)
        start = now + timedelta(hours=index)
        waitlist.append(SiteWaitlist(id=f"wl-{index:04d}", site_id=site.id, customer_id=owner.id, vehicle_id=car.id,
                                     start_at=start, end_at=start + timedelta(hours=3), status=["waiting", "offered", "cancelled"][index % 3],
                                     request_id=f"wl-req-{index:04d}", created_by_id=test_user.id, created_at=now + timedelta(minutes=index // 2)))
    db_session.add_all(reservations + allocations + waitlist)
    db_session.flush()
    for index, row in enumerate(reservations):
        row.status = ["confirmed", "cancelled", "expired"][index % 3]
    for index, row in enumerate(allocations):
        row.status = "active" if index % 5 else "cancelled"
    db_session.commit()
    actor = {"user": account}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    return SimpleNamespace(db=db_session, client=TestClient(app), actor=actor, account=account, other=other,
                           staff=test_user, staff_b=staff_b, a=a, b=b, customer=customer, customer2=customer2, now=now,
                           vehicle=vehicle, vehicle2=vehicle2)


def _pages(client, path, size=40, **params):
    seen, offset, pages = [], 0, 0
    while True:
        response = client.get(path, params={**params, "limit": size, "offset": offset})
        assert response.status_code == 200, response.text
        chunk = response.json()
        assert len(chunk) <= size
        seen.extend(chunk)
        pages += 1
        if len(chunk) < size:
            return seen, pages
        offset += size
        assert pages < 50


def _expected(env, model, **where):
    rows = env.db.query(model).filter_by(**where).all()
    return {row.id for row in rows}


def test_customer_pages_cover_every_own_reservation_at_site_without_gaps_or_duplicates(env):
    got, pages = _pages(env.client, "/api/v2/me/reservations", site_id=env.a.id)
    ids = [row["id"] for row in got]
    assert pages > 1 and len(ids) > 40
    assert len(ids) == len(set(ids))
    assert set(ids) == _expected(env, ParkingReservation, customer_id=env.customer.id, site_id=env.a.id)
    assert all(row["customer_id"] == env.customer.id and row["site_id"] == env.a.id for row in got)
    keys = [(row["start_at"], row["id"]) for row in got]
    assert keys == sorted(keys, key=lambda item: (item[0], item[1]), reverse=True)


def test_customer_filters_are_applied_before_paging_and_other_customer_sees_nothing_of_mine(env):
    got, _ = _pages(env.client, "/api/v2/me/reservations", site_id=env.b.id, status="confirmed", size=10)
    assert {row["id"] for row in got} == _expected(env, ParkingReservation, customer_id=env.customer.id,
                                                    site_id=env.b.id, status="confirmed")
    window_from = (env.now + timedelta(hours=10)).replace(tzinfo=BUSINESS_TZ).isoformat()
    window_to = (env.now + timedelta(hours=12)).replace(tzinfo=BUSINESS_TZ).isoformat()
    inside = env.client.get("/api/v2/me/reservations", params={"from_at": window_from, "to_at": window_to, "limit": 100}).json()
    assert inside and all(env.now + timedelta(hours=9) < _naive(row["start_at"]) < env.now + timedelta(hours=12) for row in inside)
    env.actor["user"] = env.other
    theirs, _ = _pages(env.client, "/api/v2/me/reservations")
    assert theirs and all(row["customer_id"] == env.customer2.id for row in theirs)
    assert {row["id"] for row in theirs}.isdisjoint(_expected(env, ParkingReservation, customer_id=env.customer.id))


def test_site_lists_are_scoped_to_membership_and_paged_stably(env):
    env.actor["user"] = env.staff
    got, pages = _pages(env.client, f"/api/v2/sites/{env.a.id}/reservations", size=25)
    assert pages > 2 and {row["id"] for row in got} == _expected(env, ParkingReservation, site_id=env.a.id)
    assert env.client.get(f"/api/v2/sites/{env.b.id}/reservations").status_code == 403
    by_vehicle = env.client.get(f"/api/v2/sites/{env.a.id}/reservations", params={"vehicle_id": env.vehicle2.id, "limit": 100}).json()
    assert by_vehicle and all(row["vehicle_id"] == env.vehicle2.id for row in by_vehicle)
    allocations = env.client.get(f"/api/v2/sites/{env.a.id}/allocations", params={"status": "active", "limit": 100}).json()
    assert {row["id"] for row in allocations} == _expected(env, GuaranteedAllocation, site_id=env.a.id, status="active")
    env.actor["user"] = env.staff_b
    got_b, _ = _pages(env.client, f"/api/v2/sites/{env.b.id}/reservations", size=30)
    assert {row["id"] for row in got_b} == _expected(env, ParkingReservation, site_id=env.b.id)
    assert env.client.get(f"/api/v2/sites/{env.a.id}/waitlist").status_code == 403


def test_waitlist_queue_order_and_customer_newest_first(env):
    env.actor["user"] = env.staff
    queue, pages = _pages(env.client, f"/api/v2/sites/{env.a.id}/waitlist", size=20, status="waiting")
    assert pages > 1 and {row["id"] for row in queue} == _expected(env, SiteWaitlist, site_id=env.a.id, status="waiting")
    keys = [(row["created_at"], row["id"]) for row in queue]
    assert keys == sorted(keys)
    env.actor["user"] = env.account
    mine, _ = _pages(env.client, "/api/v2/me/waitlist", size=30, site_id=env.b.id)
    assert {row["id"] for row in mine} == _expected(env, SiteWaitlist, customer_id=env.customer.id, site_id=env.b.id)
    keys = [(row["created_at"], row["id"]) for row in mine]
    assert keys == sorted(keys, reverse=True)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "bogus"}, {"site_id": 0}])
def test_invalid_paging_parameters_are_rejected(env, params):
    assert env.client.get("/api/v2/me/reservations", params=params).status_code == 422


def _naive(value):
    from datetime import datetime
    return datetime.fromisoformat(value).astimezone(BUSINESS_TZ).replace(tzinfo=None)
