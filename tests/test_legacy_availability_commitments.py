"""The original admission screen must offer the same usable slots as scoped operations."""
from datetime import timedelta

import pytest
from fastapi import Depends
from sqlalchemy import event

from expansion import reservations
from expansion.site_schemas import AllocationCreate
from expansion.system_router import require_legacy_workspace
from routers.parking import router as parking_router
from services.parking_service import ParkingService
from test_expansion_sites import data, env, reserve  # noqa: F401
from test_portal_api import portal  # noqa: F401
from test_timed_parking import timed  # noqa: F401


@pytest.fixture
def lot(env):
    # Exercise the real legacy boundary in its supported, single-lot context.
    env.db.delete(env.b)
    env.db.commit()
    env.client.app.include_router(parking_router, dependencies=[Depends(require_legacy_workspace)])
    return env


def available(lot):
    result = lot.client.get("/parking/available-slots")
    assert result.status_code == 200, result.text
    return result.json()


def assert_capacity(lot, *, usable, occupied=0, reserved=0):
    legacy = available(lot)
    scoped = lot.client.get(f"/api/v2/sites/{lot.a.id}/availability").json()
    stats = lot.client.get("/parking/statistics")
    assert stats.status_code == 200, stats.text
    assert legacy["total_slots"] == 1
    assert legacy["total_occupied"] == occupied
    assert legacy["total_available"] == scoped["available_now"] == usable
    assert legacy["total_reserved"] == scoped["reserved_slots"] == reserved
    assert stats.json()["available_slots"] == usable
    assert stats.json()["occupied_slots"] == occupied
    assert stats.json()["reserved_slots"] == reserved
    zone = legacy["zones"][0]
    assert zone["total_slots"] == zone["available_slots"] + zone["occupied_slots"] + zone["reserved_slots"]
    assert {row["id"] for row in zone["available_slots_list"]} == ({lot.slot.id} if usable else set())


@pytest.mark.parametrize("future", [False, True])
def test_reservation_removes_slot_from_legacy_suggestions_until_cancelled(lot, future):
    start = lot.now + timedelta(hours=1) if future else lot.now
    row = reserve(lot, start=start, end=start + timedelta(hours=2))
    assert_capacity(lot, usable=0, reserved=1)
    assert lot.slot.is_occupied is False, "A reservation is not a physically parked car"
    reservations.cancel(lot.db, lot.staff, row)
    lot.db.commit()
    assert_capacity(lot, usable=1)


def test_reservation_expiry_is_reflected_without_mutating_from_a_read(lot):
    row = reserve(lot)
    lot.clock["now"] = row.arrival_deadline
    assert_capacity(lot, usable=1)
    lot.db.refresh(row)
    assert row.status == "confirmed", "Availability GET must not perform booking maintenance"


def test_arrived_reservation_is_counted_as_occupied_only(lot):
    row = reserve(lot)
    reservations.arrive(lot.db, lot.staff, row)
    lot.db.commit()
    assert_capacity(lot, usable=0, occupied=1)


def test_guaranteed_allocation_is_not_offered_to_unscheduled_admission(lot):
    row = reservations.reserve(lot.db, lot.staff, AllocationCreate(**data(lot).model_dump()), allocation=True)
    lot.db.commit()
    assert_capacity(lot, usable=0, reserved=1)
    reservations.cancel(lot.db, lot.staff, row)
    lot.db.commit()
    assert_capacity(lot, usable=1)


def test_unpaid_capacity_hold_is_not_offered_until_order_cancelled(timed):
    context, body, slot, _rate = timed
    client, current, users, _site, _kind, _db = context
    client.app.include_router(parking_router, dependencies=[Depends(require_legacy_workspace)])
    order = client.post("/api/v2/me/orders", json=body)
    assert order.status_code == 200, order.text
    current["user"] = users[0]
    result = client.get("/parking/available-slots")
    assert result.status_code == 200, result.text
    assert result.json()["total_available"] == 0 and result.json()["total_reserved"] == 1
    assert result.json()["zones"][0]["available_slots_list"] == []
    current["user"] = users[1]
    cancelled = client.post(f"/api/v2/me/orders/{order.json()['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    current["user"] = users[0]
    restored = client.get("/parking/available-slots").json()
    assert restored["total_available"] == 1 and restored["total_reserved"] == 0
    assert restored["zones"][0]["available_slots_list"][0]["id"] == slot.id


def test_slot_commitments_do_not_add_per_slot_queries(lot):
    reserve(lot)
    sql = []

    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        sql.append(statement)

    engine = lot.db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        result = ParkingService(lot.db).get_available_slots_summary()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert result["total_reserved"] == 1
    assert len(sql) == 1 and sql[0].lstrip().upper().startswith("SELECT")
