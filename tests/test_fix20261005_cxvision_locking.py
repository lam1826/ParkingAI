"""Camera entry can run alongside counter entry on disposable PostgreSQL.

Both requests go through the real HTTP routes (FastAPI TestClient, real JWT auth):
  camera : POST /api/v2/vision/observations/{id}/process   (entry camera, registered car)
  manual : POST /api/v2/sites/{site_id}/check-in            (auto slot, walk-in car)
  arrive : POST /api/v2/sites/{site_id}/reservations/{id}/arrive
get_db is pointed at a disposable alembic-head PostgreSQL database (repo helper
_isolated_checkout_postgres). No artificial pauses: both requests are released by
a Barrier, like an operator clicking while the camera loop fires.
Control: identical race but the camera loop runs under a DIFFERENT manager.
"""
import os
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier, Lock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from core.clock import business_now
from database import get_db
from expansion.site_models import ParkingReservation, ParkingSite, SiteMembership
from expansion.vision_models import Camera, VisionObservation
from expansion.vision_passage_models import CameraAutomationPolicy
from main import app
from models import Customer, ParkingSession, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone
from services.auth_service import AuthService
from test_postgres_integration import _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="Requires an isolated local PostgreSQL service",
)

def _seed(engine, rounds, reservation=False):
    now = business_now()
    with Session(engine) as db:
        role, kind = Role(name="manager"), VehicleType(name="Race car")
        db.add_all([role, kind]); db.flush()
        users = [User(username=f"mgr-{k}", password_hash=f"unused-{k}", full_name=f"Manager {k}",
                      role_id=role.id, is_active=True) for k in "xy"]
        db.add_all(users); db.flush()
        db.add(PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=10000,
                           effective_date=(now - timedelta(days=1)).date()))
        plan = []
        for r in range(rounds):
            site = ParkingSite(name=f"Lot {r}"); db.add(site); db.flush()
            db.add_all([SiteMembership(site_id=site.id, user_id=u.id, role="manager") for u in users])
            zone = Zone(name=f"Z{r}", site_id=site.id, capacity=3); db.add(zone); db.flush()
            slots = [ParkingSlot(slot_name=f"R{r}-P{i}", vehicle_type_id=kind.id, zone_id=zone.id) for i in range(3)]
            owner = Customer(full_name=f"Owner {r}", phone_number=f"LOCAL-{r:04d}")
            db.add_all(slots + [owner]); db.flush()
            car = Vehicle(license_plate=f"30A-{100 + r:03d}.45", vehicle_type_id=kind.id, customer_id=owner.id)
            db.add(car); db.flush()
            camera = Camera(site_id=site.id, zone_id=zone.id, name="Gate", direction="entry", retention_hours=24)
            db.add(camera); db.flush()
            db.add(CameraAutomationPolicy(camera_id=camera.id, enabled=True, minimum_confidence=0.9, max_age_seconds=30,
                                          direction="entry", zone_id=zone.id, enabled_at=now - timedelta(minutes=5),
                                          updated_at=now, updated_by_id=users[0].id))
            res_id = None
            if reservation:
                res = ParkingReservation(id=str(uuid.uuid4()), site_id=site.id, slot_id=slots[1].id, customer_id=owner.id,
                                         vehicle_id=car.id, start_at=now - timedelta(minutes=1), end_at=now + timedelta(hours=2),
                                         arrival_deadline=now + timedelta(minutes=30), status="confirmed",
                                         request_id=uuid.uuid4().hex, created_by_id=users[0].id)
                db.add(res); db.flush(); res_id = res.id
            plan.append(dict(site=site.id, camera=camera.id, plate=car.license_plate, reservation=res_id))
        db.commit()
        tokens = [AuthService().create_access_token(user_id=u.id, username=u.username, role="manager",
                                                    password_hash=u.password_hash) for u in users]
        return kind.id, plan, tokens


def _observation(engine, camera_id, site_id, plate, r):
    t = business_now()
    with Session(engine) as db:
        obs = VisionObservation(camera_id=camera_id, site_id=site_id, event_id=f"evt-{r}-{uuid.uuid4().hex[:8]}",
            image_hash="0" * 64, image_bytes=b"x", image_width=16, image_height=16, observed_at=t, captured_at=t,
            capture_source="live_camera", expires_at=t + timedelta(hours=24), ocr_status="recognized",
            suggested_plate=plate, confidence=0.99, engine="yolo_rapidocr", review_status="pending",
            detections=[{"plate": plate, "confidence": 0.99, "detector_confidence": 0.99, "ocr_confidence": 0.99}])
        db.add(obs); db.commit()
        return obs.id


@contextmanager
def _pg_app(engine):
    def override_get_db():
        db = Session(engine)
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    errors, guard = [], Lock()

    def on_error(context):
        err = context.original_exception
        with guard:
            errors.append((type(err).__name__, getattr(err, "sqlstate", None), " ".join(str(err).split())[:400]))
    event.listen(engine, "handle_error", on_error)
    try:
        yield errors
    finally:
        event.remove(engine, "handle_error", on_error)
        app.dependency_overrides.pop(get_db, None)


def _race(engine, rounds, *, camera_user, other="manual"):
    kind_id, plan, tokens = _seed(engine, rounds, reservation=(other == "arrive"))
    cam_client, op_client = TestClient(app, raise_server_exceptions=False), TestClient(app, raise_server_exceptions=False)
    outcomes = []
    with _pg_app(engine) as errors:
        for r, p in enumerate(plan):
            obs_id = _observation(engine, p["camera"], p["site"], p["plate"], r)
            start = Barrier(2, timeout=10)

            def camera():
                start.wait()
                resp = cam_client.post(f"/api/v2/vision/observations/{obs_id}/process",
                                       headers={"Authorization": f"Bearer {tokens[camera_user]}"})
                body = resp.json()
                return "camera", resp.status_code, body.get("state", body.get("detail")), body.get("reason")

            def operator():
                start.wait()
                headers = {"Authorization": f"Bearer {tokens[0]}"}
                if other == "manual":
                    resp = op_client.post(f"/api/v2/sites/{p['site']}/check-in", headers=headers,
                                          json={"license_plate": f"51A-{900 + r:03d}.99", "vehicle_type_id": kind_id})
                    body = resp.json()
                    return "manual", resp.status_code, body.get("slot_name", body.get("detail"))
                resp = op_client.post(f"/api/v2/sites/{p['site']}/reservations/{p['reservation']}/arrive", headers=headers)
                body = resp.json()
                return "arrive", resp.status_code, body.get("status", body.get("detail"))

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(camera), pool.submit(operator)]
                outcomes.append(tuple(f.result(timeout=60) for f in futures))
        snapshot = list(errors)
    with Session(engine) as db:
        sessions = db.scalar(select(func.count()).select_from(ParkingSession))
    return outcomes, snapshot, sessions


def _report(label, outcomes, errors, sessions):
    deadlocks = [e for e in errors if e[1] == "40P01"]
    bad = [o for o in outcomes if any(x[1] >= 500 for x in o) or any(x[1] == 409 and "Dữ liệu vừa thay đổi" in str(x[2]) for x in o)]
    print(f"\n[{label}] ROUNDS {len(outcomes)} BAD_ROUNDS {len(bad)} DEADLOCKS {len(deadlocks)} SESSIONS {sessions}")
    print(f"[{label}] status mix: {Counter((x[0], x[1]) for o in outcomes for x in o)}")
    for o in outcomes[:3]:
        print(f"[{label}] outcome: {o}")
    if bad:
        print(f"[{label}] first bad: {bad[0]}")
    if deadlocks:
        print(f"[{label}] first deadlock: {deadlocks[0]}")
    others = [e for e in errors if e[1] != "40P01"]
    if others:
        print(f"[{label}] other DB errors: {others[:3]}")
    return bad, deadlocks


ROUNDS = 8


def test_1_camera_vs_manual_same_operator():
    with _isolated_checkout_postgres() as engine:
        outcomes, errors, sessions = _race(engine, ROUNDS, camera_user=0, other="manual")
        bad, deadlocks = _report("same-operator camera vs manual auto-slot", outcomes, errors, sessions)
        assert not deadlocks and not bad and not errors
        assert sessions == 2 * ROUNDS
        assert all(camera[1] == 200 and manual[1] == 201 for camera, manual in outcomes)


def test_2_control_camera_vs_manual_different_operator():
    with _isolated_checkout_postgres() as engine:
        outcomes, errors, sessions = _race(engine, ROUNDS, camera_user=1, other="manual")
        bad, deadlocks = _report("CONTROL different-operator camera vs manual", outcomes, errors, sessions)
        assert not deadlocks and not bad and sessions == 2 * ROUNDS


def test_3_camera_vs_arrive_same_operator():
    with _isolated_checkout_postgres() as engine:
        outcomes, errors, sessions = _race(engine, ROUNDS, camera_user=0, other="arrive")
        bad, deadlocks = _report("same-operator camera vs reservation arrive", outcomes, errors, sessions)
        assert not deadlocks and not bad and not errors
        assert sessions == ROUNDS
        assert all(camera[1] == 200 and arrive[1] == 200 for camera, arrive in outcomes)


def test_4_control_camera_vs_arrive_different_operator():
    with _isolated_checkout_postgres() as engine:
        outcomes, errors, sessions = _race(engine, ROUNDS, camera_user=1, other="arrive")
        bad, deadlocks = _report("CONTROL different-operator camera vs arrive", outcomes, errors, sessions)
        assert not deadlocks and not bad
