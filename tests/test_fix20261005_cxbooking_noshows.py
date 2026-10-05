from test_expansion_sites import env  # noqa: F401  (fixture only)

from datetime import timedelta
from sqlalchemy import select, exists

from core.clock import BUSINESS_TZ, business_now
from expansion import reservations as service
from expansion.portal_worker import run_portal_maintenance
from expansion.site_models import ParkingReservation


def _create_noshow(env, key):
    # Staff booked 60 min ago a 4-hour window; deadline = start + 15 min (45 min ago now).
    real_now = business_now().replace(microsecond=0)
    env.clock["now"] = real_now - timedelta(hours=1)
    body = {"site_id": env.a.id, "vehicle_id": env.vehicle.id, "slot_id": env.slot.id,
            "start_at": env.clock["now"].replace(tzinfo=BUSINESS_TZ).isoformat(),
            "end_at": (env.clock["now"] + timedelta(hours=4)).replace(tzinfo=BUSINESS_TZ).isoformat(),
            "request_id": key}
    r = env.client.post(f"/api/v2/sites/{env.a.id}/reservations", json=body)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    # Real time has now advanced: 45 min after arrival deadline.
    env.clock["now"] = real_now
    row = env.db.get(ParkingReservation, rid)
    print("\nreservation", rid, "start", row.start_at, "deadline", row.arrival_deadline, "end", row.end_at, "now", real_now)
    return rid


def test_staff_noshow_never_expired_by_worker_and_blocks_slot_zone(env):
    rid = _create_noshow(env, "noshow-probe-request-0001")
    for i in range(3):
        print(f"worker cycle {i+1}:", run_portal_maintenance(env.db))
    env.db.expire_all()
    row = env.db.get(ParkingReservation, rid)
    status_after_worker = row.status
    print("reservation status after 3 worker cycles:", status_after_worker)
    # Application predicate already treats it as dead:
    live = env.db.scalar(select(exists().where(ParkingReservation.id == rid, service.live_reservation(env.clock["now"]))))
    print("live_reservation(now) for the no-show:", live)
    print("has_slot_commitment (app predicate):", env.db.scalar(select(service.has_slot_commitment(env.slot.id, env.clock["now"]))))

    r = env.client.patch(f"/api/v2/sites/{env.a.id}/slots/{env.slot.id}", json={"is_active": False})
    print("PATCH slot is_active=false ->", r.status_code, r.json())
    r2 = env.client.patch(f"/api/v2/sites/{env.a.id}/zones/{env.slot.zone_id}", json={"is_active": False})
    print("PATCH zone is_active=false ->", r2.status_code, r2.json())
    r3 = env.client.post(f"/api/v2/sites/{env.a.id}/reservations/{rid}/arrive")
    print("POST arrive ->", r3.status_code, r3.json())
    lst = env.client.get(f"/api/v2/sites/{env.a.id}/reservations").json()
    print("staff list status:", [(x["id"] == rid, x["status"]) for x in lst])
    env.actor["user"] = env.account
    mine = env.client.get("/api/v2/me/reservations").json()
    print("customer list status:", [(x["id"] == rid, x["status"]) for x in mine])
    c = env.client.post(f"/api/v2/me/reservations/{rid}/cancel")
    print("customer cancel no-show ->", c.status_code, c.json().get("status"))

    assert status_after_worker == "expired"
    assert live is False
    assert r.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 409
    assert c.json()["status"] == "expired"
