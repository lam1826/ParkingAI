"""Camera entry must not deadlock with paid monthly periods for the same car.

The counter deliberately holds its vehicle lock until the real HTTP camera
request waits on a PostgreSQL lock. This exposes both an explicit operator
lock and the implicit actor FK lock of an prematurely flushed passage event.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, local
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from core.clock import business_now
from expansion.vision_passage_models import VisionPassageEvent
from expansion.vision_models import Camera
from expansion.vision_passage_schemas import AutomationPolicyUpdate
from expansion import vision_passage_service as passage_service
from main import app
from models import MonthlyPass, ParkingSession, Payment, User, Vehicle
from schemas.monthly_pass import MonthlyPassCreate, MonthlyPassRenew
from services import monthly_subscription_service as monthly_service
from test_fix20261005_cxvision_locking import _observation, _pg_app, _seed
from test_postgres_integration import _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="Requires an isolated local PostgreSQL service",
)


def _camera_waits_on_lock(engine, counter_pid):
    with engine.connect() as connection:
        return bool(connection.scalar(text(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> :counter_pid"
        ), {"counter_pid": counter_pid}))


@pytest.mark.parametrize("operation", ["sale", "renewal"])
@pytest.mark.parametrize("same_operator", [True, False], ids=["same_operator", "different_operator"])
def test_camera_entry_during_monthly_collection(monkeypatch, operation, same_operator):
    with _isolated_checkout_postgres() as engine:
        _, plan, tokens = _seed(engine, 1)
        context = plan[0]
        today = business_now().date()
        with Session(engine) as db:
            users = {user.username: user.id for user in db.scalars(select(User))}
            vehicle = db.scalar(select(Vehicle).where(Vehicle.license_plate == context["plate"]))
            vehicle_id, customer_id = vehicle.id, vehicle.customer_id
        staff_id = users["mgr-x" if same_operator else "mgr-y"]
        original_id = None
        if operation == "renewal":
            with Session(engine) as db:
                original = monthly_service.create_subscription(db, MonthlyPassCreate(
                    customer_id=customer_id, vehicle_id=vehicle_id, pass_code="PREVIOUS-PERIOD",
                    price=100000, start_date=today - timedelta(days=31), end_date=today - timedelta(days=1),
                    payment_method="cash", site_id=context["site"],
                ), staff_id)
                original_id = original.id

        observation_id = _observation(engine, context["camera"], context["site"], context["plate"], 0)
        vehicle_locked = Event()
        waited = []
        real_lock_vehicle = monthly_service._lock_vehicle

        def hold_vehicle_until_camera_waits(db, target_id):
            row = real_lock_vehicle(db, target_id)
            counter_pid = db.scalar(text("SELECT pg_backend_pid()"))
            vehicle_locked.set()
            deadline = monotonic() + 3
            while monotonic() < deadline and not _camera_waits_on_lock(engine, counter_pid):
                sleep(0.01)
            waited.append(_camera_waits_on_lock(engine, counter_pid))
            return row

        monkeypatch.setattr(monthly_service, "_lock_vehicle", hold_vehicle_until_camera_waits)

        def collect_period():
            with Session(engine) as db:
                if operation == "sale":
                    period = monthly_service.create_subscription(db, MonthlyPassCreate(
                        customer_id=customer_id, vehicle_id=vehicle_id, pass_code="NEW-PERIOD",
                        price=100000, start_date=today, end_date=today + timedelta(days=30),
                        payment_method="cash", site_id=context["site"],
                    ), staff_id)
                else:
                    period = monthly_service.renew_subscription(db, original_id, MonthlyPassRenew(
                        start_date=today, end_date=today + timedelta(days=30), price=100000,
                        payment_method="cash", site_id=context["site"], request_id="renew-camera-20261005",
                    ), staff_id)
                return period.id

        def process_camera():
            assert vehicle_locked.wait(10), "Counter did not acquire the vehicle lock"
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(f"/api/v2/vision/observations/{observation_id}/process", headers={
                    "Authorization": f"Bearer {tokens[0]}",
                })
                return response.status_code, response.json()

        with _pg_app(engine) as errors:
            with ThreadPoolExecutor(max_workers=2) as pool:
                counter = pool.submit(collect_period)
                camera = pool.submit(process_camera)
                period_id = counter.result(timeout=20)
                status, body = camera.result(timeout=20)
        assert waited == [True], "The conflicting lock window was not exercised"
        assert not errors, errors
        assert status == 200, body
        assert body["state"] == "entered", body
        with Session(engine) as db:
            assert db.get(MonthlyPass, period_id).is_active
            receipts = db.scalars(select(Payment).where(
                Payment.source_type == "monthly_pass", Payment.source_id == str(period_id), Payment.kind == "receipt",
            )).all()
            assert len(receipts) == 1 and receipts[0].collected_by_id == staff_id
            assert db.scalar(select(func.count()).select_from(ParkingSession)) == 1
            passage = db.scalar(select(VisionPassageEvent).where(VisionPassageEvent.observation_key == observation_id))
            assert passage.state == "entered" and passage.session_id == body["session_id"]


def test_camera_entry_during_same_operator_policy_update(monkeypatch):
    with _isolated_checkout_postgres() as engine:
        _, plan, tokens = _seed(engine, 1)
        context = plan[0]
        observation_id = _observation(engine, context["camera"], context["site"], context["plate"], 0)
        camera_deciding, policy_waiting = Event(), Event()
        operation = local()
        real_decide, real_camera_for = passage_service._decide, passage_service.camera_for

        def pause_entry_before_admission(*args, **kwargs):
            camera_deciding.set()
            assert policy_waiting.wait(3), "Policy did not reach the camera lock"
            return real_decide(*args, **kwargs)

        def signal_policy_camera_lock(*args, **kwargs):
            if getattr(operation, "policy", False) and kwargs.get("lock"):
                # On the buggy path the operator row is already locked here.
                policy_waiting.set()
            return real_camera_for(*args, **kwargs)

        monkeypatch.setattr(passage_service, "_decide", pause_entry_before_admission)
        monkeypatch.setattr(passage_service, "camera_for", signal_policy_camera_lock)

        def update_policy():
            assert camera_deciding.wait(10), "Entry did not hold the camera row"
            operation.policy = True
            with Session(engine) as db:
                actor = db.scalar(select(User).where(User.username == "mgr-x"))
                try:
                    return passage_service.update_policy(db, actor, context["camera"], AutomationPolicyUpdate(
                        enabled=True, minimum_confidence=0.97, max_age_seconds=15,
                    ))
                except Exception as failure:
                    return failure

        def process_camera():
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(f"/api/v2/vision/observations/{observation_id}/process", headers={
                    "Authorization": f"Bearer {tokens[0]}",
                })
                return response.status_code, response.json()

        with _pg_app(engine) as errors:
            with ThreadPoolExecutor(max_workers=2) as pool:
                camera, policy = pool.submit(process_camera), pool.submit(update_policy)
                status, body = camera.result(timeout=20)
                result = policy.result(timeout=20)
        assert not errors, errors
        assert status == 200 and body["state"] == "entered", body
        assert isinstance(result, dict) and result["enabled"], result


def test_policy_update_during_same_operator_exit(monkeypatch):
    with _isolated_checkout_postgres() as engine:
        _, plan, _ = _seed(engine, 1)
        context = plan[0]
        with Session(engine) as db:
            db.get(Camera, context["camera"]).direction = "exit"
            db.commit()
        observation_id = _observation(engine, context["camera"], context["site"], context["plate"], 0)
        policy_has_camera, exit_at_camera = Event(), Event()
        operation = local()
        real_camera_for = passage_service.camera_for

        def overlap_policy_and_exit(*args, **kwargs):
            if kwargs.get("lock") and getattr(operation, "name", None) == "exit":
                exit_at_camera.set()
            camera = real_camera_for(*args, **kwargs)
            if kwargs.get("lock") and getattr(operation, "name", None) == "policy":
                policy_has_camera.set()
                assert exit_at_camera.wait(3), "Exit did not reach the camera lock"
            return camera

        monkeypatch.setattr(passage_service, "camera_for", overlap_policy_and_exit)

        def perform(name):
            operation.name = name
            with Session(engine) as db:
                # Different from the policy's previous updater: UPDATE must run
                # the updated_by FK check against this same exit operator.
                actor = db.scalar(select(User).where(User.username == "mgr-y"))
                if name == "exit":
                    assert policy_has_camera.wait(10), "Policy did not hold the camera lock"
                try:
                    if name == "policy":
                        return passage_service.update_policy(db, actor, context["camera"], AutomationPolicyUpdate(
                            enabled=True, minimum_confidence=0.97, max_age_seconds=15,
                        ))
                    return passage_service.process_observation(db, actor, observation_id)
                except Exception as failure:
                    return failure

        with _pg_app(engine) as errors:
            with ThreadPoolExecutor(max_workers=2) as pool:
                policy, exit_request = pool.submit(perform, "policy"), pool.submit(perform, "exit")
                updated = policy.result(timeout=20)
                processed = exit_request.result(timeout=20)
        assert not errors, errors
        assert isinstance(updated, dict) and updated["enabled"], updated
        assert isinstance(processed, dict) and processed["state"] == "manual", processed
