"""Review 28/10/2026 R2-01: verified-owner precedence for declared bookings.

Booking by declared plate/type without ownership approval stays possible for a
plate or code not verified to any customer profile and for the declarer's own
verified vehicle (DECISIONS 2026-09-23, narrowed 28/10/2026). A declaration
never matches or observes a vehicle verified to another profile: it is refused
at creation with one message that reveals neither the registered type nor the
owner's commitments, it is released where ownership is assigned (portal
approval, account link approval, staff vehicle create/update), a row left from
before the fix is never consumed by the owner's car, and customer views carry
no session id. Such a row from before the fix still blocks the owner's own
bookings of the plate until the deploy step releases it
(test_fix_r2_01_release_foreign_command.py) or its arrival deadline passes.
"""
from datetime import timedelta

from sqlalchemy import func, select

from core.clock import BUSINESS_TZ, business_now
from core.vehicle_identity import canonical_identity, lock_identity
from expansion import declared_bookings
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.simplified_customer_router import router as simplified_router
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from routers.vehicle import router as vehicle_router
from test_expansion_sites import env, reserve  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401
from test_timed_parking import timed  # noqa: F401

REFUSED = ("Không thể đặt trước cho biển số/mã xe này với loại xe đã chọn. Hãy kiểm tra lại biển số, loại xe "
    "hoặc liên hệ bãi để được hỗ trợ.")
FOREIGN = "Đặt trước này không thuộc tài khoản của chủ xe đã xác minh. Hãy tiếp nhận xe như lượt vào thường."


def _at(e, minutes):
    return (e.now + timedelta(minutes=minutes)).replace(tzinfo=BUSINESS_TZ).isoformat()


def _iso(value):
    return value.replace(tzinfo=BUSINESS_TZ).isoformat()


def _alternate_slot(e):
    e.slot.zone.capacity += 1
    slot = ParkingSlot(zone_id=e.slot.zone_id, vehicle_type_id=e.slot.vehicle_type_id, slot_name="ALT")
    e.db.add(slot)
    e.db.commit()
    return slot


def _check_in(e, plate, **extra):
    e.actor["user"] = e.staff
    return e.client.post(f"/api/v2/sites/{e.a.id}/check-in",
        json={"license_plate": plate, "vehicle_type_id": e.slot.vehicle_type_id, **extra})


def _statuses(e, user):
    e.actor["user"] = user
    return [item["status"] for item in e.client.get("/api/v2/me/advance-bookings").json()["items"]]


def test_a_plate_verified_to_another_profile_gets_one_refusal_for_every_type_and_window(customer_env):
    e = customer_env
    other = VehicleType(name="Xe máy", is_active=True)
    e.db.add(other)
    e.db.commit()
    reserve(e)  # a staff reservation for e.vehicle, now..now+2h
    e.actor["user"] = e.stranger
    attempts = [(e.vehicle.vehicle_type_id, 10, 60), (other.id, 10, 60),
                (e.vehicle.vehicle_type_id, 180, 240), (other.id, 180, 240)]
    for index, (kind, start, end) in enumerate(attempts):
        response = post_booking(e, license_plate=e.vehicle.license_plate, vehicle_type_id=kind,
            start_at=_at(e, start), end_at=_at(e, end), request_id=f"verified-plate-{index:04d}")
        assert response.status_code == 409 and response.json()["detail"] == REFUSED, (index, response.text)
    # A known plate nobody owns, sent with another type, gets the same answer.
    walk_in = Vehicle(license_plate="51C-123.45", vehicle_type_id=e.vehicle.vehicle_type_id)
    e.db.add(walk_in)
    e.db.commit()
    response = post_booking(e, license_plate=walk_in.license_plate, vehicle_type_id=other.id,
        request_id="walk-in-other-type-0001")
    assert response.status_code == 409 and response.json()["detail"] == REFUSED, response.text
    assert e.db.scalar(select(func.count()).select_from(DeclaredParkingReservation)) == 0


def test_manager_approval_releases_a_foreign_declaration_and_the_owner_books(timed):
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    client.app.include_router(simplified_router, prefix="/api/v2")
    plate, start = "30A-55566", (business_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    declaration = {"site_id": site.id, "license_plate": plate, "vehicle_type_id": kind.id,
        "start_at": _iso(start), "end_at": _iso(start + timedelta(hours=4)), "request_id": "foreign-before-approval"}
    current["user"] = users[2]
    foreign = client.post("/api/v2/me/advance-bookings", json=declaration)
    assert foreign.status_code == 201, foreign.text
    current["user"] = users[1]
    requested = client.post("/api/v2/me/vehicle-requests", json={"license_plate": plate, "vehicle_type_id": kind.id})
    assert requested.status_code == 200, requested.text
    current["user"] = users[0]
    approved = client.post(f"/api/v2/portal/admin/vehicle-requests/{requested.json()['id']}/resolve", json={"approve": True})
    assert approved.status_code == 200, approved.text
    db.expire_all()
    assert db.get(DeclaredParkingReservation, foreign.json()["id"]).status == "cancelled"
    current["user"] = users[1]
    vehicle_id = next(row["id"] for row in client.get("/api/v2/me/vehicles").json()["items"] if row["license_plate"] == plate)
    order = client.post("/api/v2/me/orders", json={**body, "vehicle_id": vehicle_id, "idempotency_key": "owner-after-release-0001",
        "start_at": _iso(start)})
    assert order.status_code == 200, order.text
    own = client.post("/api/v2/me/advance-bookings", json={**declaration, "start_at": _iso(start + timedelta(hours=2)),
        "request_id": "owner-after-release-0001"})
    assert own.status_code == 201, own.text
    current["user"] = users[2]
    assert [row["status"] for row in client.get("/api/v2/me/advance-bookings").json()["items"]] == ["cancelled"]


def test_linking_another_account_to_the_profile_releases_the_previous_account_declarations(timed):
    """Review round 2 (BD-3): an admin unlinks the account, another account is linked to the
    profile; the earlier account's live declaration of the profile's plate becomes foreign and
    is released when the new account is linked, so it never blocks the new owner."""
    portal, body, slot, rate = timed
    client, current, users, site, kind, db = portal
    client.app.include_router(simplified_router, prefix="/api/v2")
    slot.zone.capacity = 3
    db.add_all([ParkingSlot(slot_name=f"T-{index}", zone_id=slot.zone_id, vehicle_type_id=kind.id) for index in (2, 3)])
    db.commit()
    plate, start = "30A-12345", (business_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    current["user"] = users[1]
    previous = client.post("/api/v2/me/advance-bookings", json={"site_id": site.id, "license_plate": plate,
        "vehicle_type_id": kind.id, "start_at": _iso(start), "end_at": _iso(start + timedelta(hours=4)),
        "request_id": "previous-account-own-01"})
    assert previous.status_code == 201, previous.text
    current["user"] = users[0]
    assert client.delete(f"/api/v2/portal/admin/account-links/{users[1].id}").status_code == 204
    db.expire_all()
    # Unlinking alone releases nothing: the row holds its slot until a new owner account is linked.
    assert db.get(DeclaredParkingReservation, previous.json()["id"]).status == "confirmed"
    current["user"] = users[2]
    link = client.post("/api/v2/me/link-requests", json={"phone_number": "0901234567"})
    assert link.status_code == 200, link.text
    current["user"] = users[0]
    resolved = client.post(f"/api/v2/portal/admin/link-requests/{link.json()['id']}/resolve", json={"approve": True})
    assert resolved.status_code == 200, resolved.text
    db.expire_all()
    assert db.get(DeclaredParkingReservation, previous.json()["id"]).status == "cancelled"
    current["user"] = users[2]
    vehicle_id = next(row["id"] for row in client.get("/api/v2/me/vehicles").json()["items"] if row["license_plate"] == plate)
    order = client.post("/api/v2/me/orders", json={**body, "vehicle_id": vehicle_id, "idempotency_key": "relinked-owner-0001",
        "start_at": _iso(start)})
    assert order.status_code == 200, order.text
    own = client.post("/api/v2/me/advance-bookings", json={"site_id": site.id, "license_plate": plate,
        "vehicle_type_id": kind.id, "start_at": _iso(start + timedelta(hours=2)), "end_at": _iso(start + timedelta(hours=3)),
        "request_id": "relinked-owner-own-01"})
    assert own.status_code == 201, own.text


def test_staff_vehicle_create_and_update_with_an_owner_release_foreign_declarations(customer_env):
    e = customer_env
    e.client.app.include_router(vehicle_router, prefix="/api/v1/vehicles")
    _alternate_slot(e)
    # Create: a stranger declared a plate nobody had registered; the owner's own
    # declaration of it (another window) stays.
    foreign = post_booking(e, license_plate="51C-111.22", request_id="foreign-before-create-01")
    assert foreign.status_code == 201, foreign.text
    e.actor["user"] = e.account
    own = post_booking(e, license_plate="51C-111.22", start_at=_at(e, 180), end_at=_at(e, 240),
        request_id="owner-before-create-001")
    assert own.status_code == 201, own.text
    e.actor["user"] = e.staff
    created = e.client.post("/api/v1/vehicles", json={"license_plate": "51C-111.22",
        "vehicle_type_id": e.slot.vehicle_type_id, "customer_id": e.customer.id})
    assert created.status_code == 201, created.text
    e.db.expire_all()
    assert e.db.get(DeclaredParkingReservation, foreign.json()["id"]).status == "cancelled"
    assert e.db.get(DeclaredParkingReservation, own.json()["id"]).status == "confirmed"
    # Update: a walk-in vehicle gets its owner assigned by staff.
    walk_in = Vehicle(license_plate="51C-333.44", vehicle_type_id=e.slot.vehicle_type_id)
    e.db.add(walk_in)
    e.db.commit()
    e.actor["user"] = e.stranger
    later = post_booking(e, license_plate=walk_in.license_plate, request_id="foreign-before-update-01")
    assert later.status_code == 201, later.text
    e.actor["user"] = e.staff
    updated = e.client.put(f"/api/v1/vehicles/{walk_in.id}", json={"customer_id": e.customer.id})
    assert updated.status_code == 200 and updated.json()["customer_id"] == e.customer.id, updated.text
    e.db.expire_all()
    assert e.db.get(DeclaredParkingReservation, later.json()["id"]).status == "cancelled"
    assert _statuses(e, e.stranger) == ["cancelled", "cancelled"]


def test_a_row_left_from_before_the_fix_never_observes_the_owner_arrival(customer_env):
    e = customer_env
    alternate = _alternate_slot(e)
    start = e.now + timedelta(minutes=10)
    row = DeclaredParkingReservation(site_id=e.a.id, slot_id=e.slot.id, user_id=e.stranger.id,
        license_plate=e.vehicle.license_plate, normalized_plate=canonical_identity(e.vehicle.license_plate),
        vehicle_type_id=e.vehicle.vehicle_type_id, start_at=start, end_at=start + timedelta(hours=2),
        arrival_deadline=start + timedelta(minutes=15), request_id="declared-before-the-fix-01")
    e.db.add(row)
    e.db.commit()
    e.clock["now"] = start
    refused = _check_in(e, e.vehicle.license_plate, declared_booking_id=row.id)
    assert refused.status_code == 409 and refused.json()["detail"] == FOREIGN, refused.text
    entered = _check_in(e, e.vehicle.license_plate)
    assert entered.status_code == 201, entered.text
    assert e.db.get(ParkingSession, entered.json()["session_id"]).parking_slot_id == alternate.id
    e.db.refresh(row)
    assert row.status == "confirmed" and row.session_id is None
    e.clock["now"] = row.arrival_deadline + timedelta(seconds=1)
    e.actor["user"] = e.stranger
    items = e.client.get("/api/v2/me/advance-bookings").json()["items"]
    assert [item["status"] for item in items] == ["expired"] and "session_id" not in items[0]


def test_customer_views_omit_the_session_id_and_staff_reception_keeps_it(customer_env):
    e = customer_env
    _alternate_slot(e)  # the arrived stay keeps its slot; a later declaration needs another
    created = post_booking(e)
    assert created.status_code == 201 and "session_id" not in created.json(), created.text
    e.clock["now"] += timedelta(minutes=10)
    arrival = _check_in(e, "51A-887.76")
    assert arrival.status_code == 201, arrival.text
    staff = e.client.get(f"/api/v2/sites/{e.a.id}/advance-bookings").json()["items"]
    assert staff[0]["user_id"] == e.stranger.id and staff[0]["session_id"] == arrival.json()["session_id"]
    e.actor["user"] = e.stranger
    items = e.client.get("/api/v2/me/advance-bookings").json()["items"]
    assert [item["status"] for item in items] == ["arrived"] and "session_id" not in items[0]
    assert items[0]["slot_name"] == e.slot.slot_name
    second = post_booking(e, start_at=_at(e, 300), end_at=_at(e, 360), request_id="second-declaration-01")
    assert second.status_code == 201, second.text
    cancelled = e.client.post(f"/api/v2/me/advance-bookings/{second.json()['id']}/cancel")
    assert cancelled.status_code == 200 and "session_id" not in cancelled.json(), cancelled.text


def test_controls_own_vehicle_unregistered_plate_and_replay_still_work(customer_env):
    """Controls (green before and after the fix): what R2-01 must not take away."""
    e = customer_env
    _alternate_slot(e)
    e.actor["user"] = e.account
    body = dict(license_plate=e.vehicle.license_plate, vehicle_type_id=e.vehicle.vehicle_type_id,
        request_id="owner-own-vehicle-01")
    own = post_booking(e, **body)
    assert own.status_code == 201, own.text
    assert post_booking(e, **body).json()["id"] == own.json()["id"]
    e.actor["user"] = e.stranger
    unregistered = post_booking(e, request_id="unregistered-plate-01")
    assert unregistered.status_code == 201, unregistered.text
    assert post_booking(e, request_id="unregistered-plate-01").json()["id"] == unregistered.json()["id"]
    e.clock["now"] += timedelta(minutes=10)
    for plate, created in ((e.vehicle.license_plate, own), ("51A-887.76", unregistered)):
        arrival = _check_in(e, plate)
        assert arrival.status_code == 201, arrival.text
        e.db.expire_all()
        row = e.db.get(DeclaredParkingReservation, created.json()["id"])
        assert row.status == "arrived" and row.session_id == arrival.json()["session_id"]
    assert _statuses(e, e.account) == ["arrived"]
    assert _statuses(e, e.stranger) == ["arrived"]


def test_assigning_an_owner_releases_only_foreign_declarations(customer_env):
    """The service step the portal approval runs under the identity lock when it assigns the owner."""
    e = customer_env
    _alternate_slot(e)
    walk_in = Vehicle(license_plate="51C-246.80", vehicle_type_id=e.slot.vehicle_type_id)
    e.db.add(walk_in)
    e.db.commit()
    foreign = post_booking(e, license_plate=walk_in.license_plate, request_id="foreign-walk-in-0001")
    assert foreign.status_code == 201, foreign.text
    e.actor["user"] = e.account
    own = post_booking(e, license_plate=walk_in.license_plate, start_at=_at(e, 180), end_at=_at(e, 240),
        request_id="owner-walk-in-00001")
    assert own.status_code == 201, own.text
    lock_identity(e.db, walk_in.vehicle_type_id, walk_in.license_plate)
    walk_in.customer_id = e.customer.id
    declared_bookings.release_foreign(e.db, walk_in)
    e.db.commit()
    assert e.db.get(DeclaredParkingReservation, foreign.json()["id"]).status == "cancelled"
    assert e.db.get(DeclaredParkingReservation, own.json()["id"]).status == "confirmed"
    # A plate nobody owns releases nothing.
    unowned = post_booking(e, request_id="unowned-plate-000001")
    assert unowned.status_code == 201, unowned.text
    declared_bookings.release_foreign(e.db, Vehicle(license_plate="51A-887.76", vehicle_type_id=e.slot.vehicle_type_id))
    e.db.commit()
    assert e.db.get(DeclaredParkingReservation, unowned.json()["id"]).status == "confirmed"


def test_the_customer_list_filters_live_holds_like_the_staff_list(customer_env):
    """Round 2 (G6 d): the page loads every live hold with status=confirmed, whatever history page it shows."""
    e = customer_env
    _alternate_slot(e)
    live = post_booking(e, start_at=_at(e, 300), end_at=_at(e, 360), request_id="live-hold-filter-01")
    gone = post_booking(e, request_id="cancelled-filter-0001")
    assert live.status_code == 201 and gone.status_code == 201, (live.text, gone.text)
    assert e.client.post(f"/api/v2/me/advance-bookings/{gone.json()['id']}/cancel").status_code == 200
    past = post_booking(e, start_at=_at(e, 20), end_at=_at(e, 40), request_id="expired-filter-00001")
    assert past.status_code == 201, past.text
    e.clock["now"] += timedelta(minutes=36)
    listed = lambda **params: [row["id"] for row in e.client.get("/api/v2/me/advance-bookings", params=params).json()["items"]]
    assert listed(status="confirmed") == [live.json()["id"]]
    assert listed(status="expired") == [past.json()["id"]]
    assert listed(status="cancelled") == [gone.json()["id"]]
    assert len(listed()) == 3
    assert e.client.get("/api/v2/me/advance-bookings", params={"status": "released"}).status_code == 422
