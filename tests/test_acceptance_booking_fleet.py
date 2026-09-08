"""Independent acceptance for the booking pages and deliberately narrow fleet output."""
from datetime import timedelta, timezone

import pytest

from core.clock import BUSINESS_TZ
from expansion.site_models import GuaranteedAllocation, ParkingReservation, SiteWaitlist
from expansion.site_service import fleet_summary
from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.zone import Zone
from test_expansion_booking_pagination import env as booking_env  # noqa: F401
from test_expansion_fleet_report import env as fleet_env, SESSION_KEYS  # noqa: F401


ENDPOINTS = [
    ("me/reservations", ParkingReservation, "confirmed", True),
    ("me/waitlist", SiteWaitlist, "waiting", True),
    ("sites/{site}/reservations", ParkingReservation, "confirmed", False),
    ("sites/{site}/allocations", GuaranteedAllocation, "active", False),
    ("sites/{site}/waitlist", SiteWaitlist, "waiting", False),
]


def _at(value):
    return value.replace(tzinfo=BUSINESS_TZ).isoformat()


def _add_dense_bookings(env, model, status):
    """120 matching rows plus interleaved foreign-site/foreign-customer rows.

    Both authorized customers at A share start/created timestamps, forcing real
    ties within a filtered site page rather than ties only across different sites.
    """
    slot_a = env.db.query(ParkingSlot).join(Zone).filter(Zone.site_id == env.a.id).first()
    spare = ParkingSlot(zone_id=slot_a.zone_id,
                        vehicle_type_id=env.vehicle.vehicle_type_id, slot_name="acceptance-A-spare")
    env.db.add(spare)
    env.db.flush()
    slot_b = env.db.query(ParkingSlot).filter_by(slot_name="B-01").one()
    expected = {"mine": [], "site": []}
    base = env.now + timedelta(days=180)
    for index in range(120):
        for label, site, slot, owner, car in (
            ("mine", env.a, slot_a, env.customer, env.vehicle),
            ("foreign-site", env.b, slot_b, env.customer, env.vehicle),
            ("other-customer", env.a, spare, env.customer2, env.vehicle2),
        ):
            start = base + timedelta(hours=index * 2)
            identifier = f"accept-{label}-{index:03}"
            values = dict(id=identifier, site_id=site.id, customer_id=owner.id, vehicle_id=car.id,
                          start_at=start, end_at=start + timedelta(hours=1), status=status,
                          request_id=identifier, created_by_id=env.staff.id, created_at=base)
            if model is not SiteWaitlist:
                values["slot_id"] = slot.id
            if model is ParkingReservation:
                values["arrival_deadline"] = start + timedelta(minutes=15)
            env.db.add(model(**values))
            if label == "mine":
                expected["mine"].append(identifier)
            if site.id == env.a.id:
                expected["site"].append(identifier)
    env.db.commit()
    return base, expected


@pytest.mark.parametrize("endpoint,model,status,is_customer", ENDPOINTS)
def test_every_booking_endpoint_reaches_beyond_100_after_scope_filters(booking_env, endpoint, model, status, is_customer):
    env = booking_env
    base, expected = _add_dense_bookings(env, model, status)
    env.actor["user"] = env.account if is_customer else env.staff
    path = "/api/v2/" + endpoint.format(site=env.a.id)
    params = {"status": status, "from_at": _at(base), "to_at": _at(base + timedelta(days=10)), "limit": 25}
    if is_customer:
        params["site_id"] = env.a.id
    collected = []
    for offset in range(0, 275, 25):
        result = env.client.get(path, params={**params, "offset": offset})
        assert result.status_code == 200, result.text
        page = result.json()
        collected.extend(page)
        if len(page) < 25:
            break
    ids = [row["id"] for row in collected]
    assert len(ids) > 100 and len(ids) == len(set(ids))
    assert set(ids) == set(expected["mine" if is_customer else "site"])
    assert all(row["site_id"] == env.a.id for row in collected)
    if is_customer:
        assert all(row["customer_id"] == env.customer.id for row in collected)
    order_field = "created_at" if model is SiteWaitlist else "start_at"
    keys = [(row[order_field], row["id"]) for row in collected]
    assert keys == sorted(keys, reverse=is_customer or model is not SiteWaitlist)
    if not is_customer:
        env.actor["user"] = env.staff_b
        forbidden = env.client.get(path, params={**params, "offset": 100})
        assert forbidden.status_code == 403


@pytest.mark.parametrize("endpoint,model,status,is_customer", ENDPOINTS)
@pytest.mark.parametrize("minutes", [0, -30])
def test_non_positive_booking_filter_window_is_rejected(booking_env, endpoint, model, status, is_customer, minutes):
    env = booking_env
    env.actor["user"] = env.account if is_customer else env.staff
    start = env.now + (timedelta(days=32, minutes=60) if model is GuaranteedAllocation else timedelta(hours=10, minutes=30))
    response = env.client.get("/api/v2/" + endpoint.format(site=env.a.id), params={
        "from_at": _at(start), "to_at": _at(start + timedelta(minutes=minutes)), "limit": 25,
    })
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("endpoint,model,status,is_customer", ENDPOINTS)
def test_booking_window_uses_overlap_and_normalizes_offsets_before_filtering(booking_env, endpoint, model, status, is_customer):
    env = booking_env
    env.actor["user"] = env.account if is_customer else env.staff
    scoped = env.db.query(model).filter_by(site_id=env.a.id)
    if is_customer:
        scoped = scoped.filter_by(customer_id=env.customer.id)
    rows = scoped.all()
    reference = rows[0]
    path = "/api/v2/" + endpoint.format(site=env.a.id)
    start = reference.start_at + timedelta(minutes=15)
    end = reference.end_at - timedelta(minutes=15)
    lower_utc = start.replace(tzinfo=BUSINESS_TZ).astimezone(timezone.utc).isoformat()
    params = {"from_at": lower_utc, "to_at": _at(end), "limit": 100}
    if is_customer:
        params["site_id"] = env.a.id
    response = env.client.get(path, params=params)
    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()}
    assert reference.id in ids  # Booking starts before the lower bound but still overlaps.
    assert ids == {row.id for row in rows if row.end_at > start and row.start_at < end}
    # Half-open overlap excludes a booking that ends exactly at the lower bound.
    ending = env.client.get(path, params={**params, "from_at": _at(reference.end_at),
                                         "to_at": _at(reference.end_at + timedelta(hours=1))})
    assert ending.status_code == 200 and reference.id not in {row["id"] for row in ending.json()}
    starting = env.client.get(path, params={**params, "from_at": _at(reference.start_at - timedelta(hours=1)),
                                           "to_at": _at(reference.start_at)})
    assert starting.status_code == 200 and reference.id not in {row["id"] for row in starting.json()}
    # Different offsets can still represent the same instant and form an empty interval.
    same_instant = env.client.get(path, params={**params, "to_at": _at(start)})
    assert same_instant.status_code == 422, same_instant.text


def test_fleet_totals_and_exact_dto_cover_more_than_100_sessions(fleet_env):
    env = fleet_env
    rows = []
    for index in range(125):
        start = env.now - timedelta(minutes=50) + timedelta(seconds=index)
        row = ParkingSession(id=f"acceptance-fleet-{index:03}", vehicle_id=env.vehicle.id,
                             parking_slot_id=env.slot.id, check_in_time=start,
                             check_out_time=start + timedelta(seconds=1), parking_fee=1_000 + index,
                             status="completed", staff_in_id=env.staff.id, staff_out_id=env.staff.id)
        env.db.add(row)
        rows.append(row)
    env.db.commit()
    ids = []
    for offset in (0, 50, 100, 150):
        summary = fleet_summary(env.db, env.account, env.org.id, limit=50, offset=offset)
        assert summary["total_sessions"] == summary["completed_sessions"] == 125
        assert summary["active_sessions"] == 0
        assert summary["parking_fees"] == sum(1_000 + index for index in range(125))
        assert all(set(row) == SESSION_KEYS for row in summary["sessions"])
        ids.extend(row["id"] for row in summary["sessions"])
    assert ids == [row.id for row in reversed(rows)]
    assert len(ids) == len(set(ids)) == 125
