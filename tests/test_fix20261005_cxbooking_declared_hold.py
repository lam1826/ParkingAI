import time
from datetime import timedelta

from sqlalchemy import select, func

from core.clock import BUSINESS_TZ, business_now
from expansion import reservations as reservations_mod
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.simplified_customer_router import router as declared_router
from expansion.site_router import router as site_router
from expansion.timed_parking_models import ParkingCapacityHold
from models.parking_session import ParkingSession
from test_portal_api import portal  # noqa: F401
from test_timed_parking import timed  # noqa: F401

PLATE = "51F-99999"


def _iso(value):
    return value.replace(tzinfo=BUSINESS_TZ).isoformat()


def _setup(timed, with_order):
    portal_, body, slot, rate = timed
    client, current, users, site, kind, db = portal_
    client.app.include_router(declared_router, prefix="/api/v2")
    client.app.include_router(site_router)
    now = business_now().replace(microsecond=0)
    # Declared booking starts 3 s from now, so the real clock (no monkeypatch)
    # is inside the booking window after a short sleep.
    d_start, d_end = now + timedelta(seconds=3), now + timedelta(minutes=60)
    current["user"] = users[2]
    booking = client.post("/api/v2/me/advance-bookings", json={"site_id": site.id, "license_plate": PLATE,
        "vehicle_type_id": kind.id, "start_at": _iso(d_start), "end_at": _iso(d_end),
        "request_id": "declared-vs-hold-%d" % int(with_order)})
    print("\n[declared booking]", booking.status_code, booking.json().get("slot_name"),
          booking.json().get("start_at"), "->", booking.json().get("end_at"))
    assert booking.status_code == 201, booking.text
    if with_order:
        current["user"] = users[1]
        order = client.post("/api/v2/me/orders", json=dict(body, start_at=_iso(d_end),
                                                           idempotency_key="purchase-after-declared-1"))
        print("[prepaid order]", order.status_code, order.json().get("status"), order.json().get("slot"))
        assert order.status_code == 200, order.text
        hold = db.scalar(select(ParkingCapacityHold))
        print("[hold]", "slot", hold.slot_id, "start", hold.start_at, "end", hold.end_at,
              "expires", hold.expires_at, hold.status)
        assert hold.slot_id == slot.id and hold.start_at == d_end
    time.sleep(4)  # real clock now inside [d_start, arrival_deadline)
    return client, current, users, site, kind, db, slot, d_end


def _check_in(client, current, users, site, kind, monkeypatch):
    seen = []
    original = reservations_mod.admission_allowed

    def spy(*args, **kwargs):
        result = original(*args, **kwargs)
        seen.append(result)
        return result
    monkeypatch.setattr(reservations_mod, "admission_allowed", spy)
    import services.parking_service as ps
    orig_map = ps.map_check_in_integrity_error

    def map_spy(exc):
        print("[DB error raised by trigger]", str(exc.orig))
        return orig_map(exc)
    monkeypatch.setattr(ps, "map_check_in_integrity_error", map_spy)
    current["user"] = users[0]  # admin/staff at the gate
    response = client.post(f"/api/v2/sites/{site.id}/check-in",
                           json={"license_plate": PLATE, "vehicle_type_id": kind.id})
    print("[admission_allowed results]", seen)
    print("[check-in]", response.status_code, response.json())
    return response, seen


def test_control_declared_holder_checks_in_without_hold(timed, monkeypatch):
    client, current, users, site, kind, db, slot, _ = _setup(timed, with_order=False)
    response, seen = _check_in(client, current, users, site, kind, monkeypatch)
    assert response.status_code == 201, response.text
    assert response.json()["slot_name"] == "T-1"


def test_declared_holder_blocked_by_later_non_overlapping_hold(timed, monkeypatch):
    client, current, users, site, kind, db, slot, d_end = _setup(timed, with_order=True)
    response, seen = _check_in(client, current, users, site, kind, monkeypatch)
    # Application predicate admits the declared holder ...
    assert seen and seen[0] is True
    assert response.status_code == 201, response.text
    assert db.scalar(select(func.count()).select_from(ParkingSession)) == 1
    booking = db.scalar(select(DeclaredParkingReservation))
    assert booking.status == 'arrived' and booking.session_id == response.json()['session_id']
