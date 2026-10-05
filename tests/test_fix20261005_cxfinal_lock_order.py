"""Real PostgreSQL races: counter money, camera passage and reservation arrival.

Scheduling pauses expose the conflicting row-lock window; business code and
the HTTP passage/arrival routes execute unchanged against migrated databases.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from core.clock import business_now
from expansion.vision_models import Camera
from expansion.vision_passage_models import CameraAutomationPolicy
from main import app
from models import CashShift, MonthlyPass, ParkingSession, Payment, User, Vehicle
from schemas.monthly_pass import MonthlyPassCreate, MonthlyPassRenew
from services import monthly_subscription_service as monthly_service
from services.cash_shift_service import CashShiftService
from services.parking_service import ParkingService
from test_fix20261005_cxvision_locking import _observation, _pg_app, _seed
from test_postgres_integration import _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"), reason="Requires an isolated local PostgreSQL service",
)


def _blocked_by(engine, holder_pid):
    with engine.connect() as connection:
        return connection.scalar(text(
            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
            "WHERE datname=current_database() AND :holder = ANY(pg_blocking_pids(pid)))"
        ), {"holder": holder_pid})


def _wait_for_block(engine, holder_pid):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        if _blocked_by(engine, holder_pid):
            return True
        sleep(0.01)
    return False


def _car_and_staff(engine, context, same_operator=True):
    with Session(engine) as db:
        users = {user.username: user.id for user in db.scalars(select(User))}
        car = db.scalar(select(Vehicle).where(Vehicle.license_plate == context["plate"]))
        return car.id, car.customer_id, users["mgr-x" if same_operator else "mgr-y"], users["mgr-x"]


def _sell(db, vehicle_id, customer_id, staff_id, site_id, start, end, code):
    return monthly_service.create_subscription(db, MonthlyPassCreate(
        customer_id=customer_id, vehicle_id=vehicle_id, pass_code=code,
        price=100000, start_date=start, end_date=end, payment_method="cash", site_id=site_id,
    ), staff_id)


@pytest.mark.parametrize("operation", ["sale", "renewal"])
@pytest.mark.parametrize("other", ["exit", "arrive"])
@pytest.mark.parametrize("same_operator", [True, False], ids=["same_operator", "different_operator"])
def test_monthly_counter_race_with_exit_or_arrival(monkeypatch, operation, other, same_operator):
    with _isolated_checkout_postgres() as engine:
        kind_id, plan, tokens = _seed(engine, 1, reservation=other == "arrive")
        context = plan[0]
        vehicle_id, customer_id, staff_id, passage_staff_id = _car_and_staff(engine, context, same_operator)
        today = business_now().date()
        original_id = None
        if other == "exit" or operation == "renewal":
            end = today + timedelta(days=2) if other == "exit" else today - timedelta(days=1)
            with Session(engine) as db:
                original_id = _sell(db, vehicle_id, customer_id, staff_id, context["site"],
                    today - timedelta(days=31), end, "ORIGINAL-PERIOD").id
        if other == "exit":
            with Session(engine) as db:
                admitted = ParkingService(db).check_in(context["plate"], kind_id, passage_staff_id,
                    _expected_site_id=context["site"])
                assert admitted["monthly_pass_id"] == original_id
                session_id = admitted["session_id"]
            with Session(engine) as db:
                db.get(Camera, context["camera"]).direction = "exit"
                db.get(CameraAutomationPolicy, context["camera"]).direction = "exit"
                db.commit()
            observation_id = _observation(engine, context["camera"], context["site"], context["plate"], 0)
        start = today + timedelta(days=3) if other == "exit" else today
        with Session(engine) as db:
            shift = CashShiftService.open_shift(db, db.get(User, staff_id), site_id=context["site"])
            db.commit()
            shift_id = shift.id

        counter_locked, exercised = Event(), []
        real_lock = monthly_service._lock_vehicle

        def hold_counter_vehicle(db, target_id):
            row = real_lock(db, target_id)
            # Arrival also calls this helper. Pause only the counter session.
            if db.info.get("counter"):
                holder_pid = db.scalar(text("SELECT pg_backend_pid()"))
                counter_locked.set()
                exercised.append(_wait_for_block(engine, holder_pid))
            return row

        monkeypatch.setattr(monthly_service, "_lock_vehicle", hold_counter_vehicle)

        def collect():
            with Session(engine, info={"counter": True}) as db:
                if operation == "sale":
                    period = _sell(db, vehicle_id, customer_id, staff_id, context["site"],
                        start, start + timedelta(days=30), "NEW-COUNTER-PERIOD")
                else:
                    period = monthly_service.renew_subscription(db, original_id, MonthlyPassRenew(
                        start_date=start, end_date=start + timedelta(days=30), price=100000,
                        payment_method="cash", site_id=context["site"], request_id="renew-final-lock-order",
                    ), staff_id)
                return period.id

        def passage():
            assert counter_locked.wait(10), "Counter did not reach the vehicle lock"
            url = (f"/api/v2/vision/observations/{observation_id}/process" if other == "exit" else
                f"/api/v2/sites/{context['site']}/reservations/{context['reservation']}/arrive")
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(url, headers={"Authorization": f"Bearer {tokens[0]}"})
                return response.status_code, response.json()

        with _pg_app(engine) as errors:
            with ThreadPoolExecutor(max_workers=2) as pool:
                counter, other_request = pool.submit(collect), pool.submit(passage)
                period_id = counter.result(timeout=20)
                status, body = other_request.result(timeout=20)
        assert exercised == [True], "The competing transaction never waited on the counter"
        assert not errors, errors
        assert status == 200, body
        assert body["state" if other == "exit" else "status"] == ("exited" if other == "exit" else "arrived"), body
        with Session(engine) as db:
            period = db.get(MonthlyPass, period_id)
            assert period.is_active and period.start_date == start
            receipts = db.scalars(select(Payment).where(Payment.source_type == "monthly_pass",
                Payment.source_id == str(period_id), Payment.kind == "receipt")).all()
            assert len(receipts) == 1 and receipts[0].amount == 100000
            assert receipts[0].collected_by_id == staff_id and receipts[0].shift_id == shift_id
            assert CashShiftService.get_summary(db, shift_id, db.get(User, staff_id))["expected_cash"] == 100000
            if other == "exit":
                assert db.get(ParkingSession, session_id).status == "completed"


@pytest.mark.parametrize("operation", ["sale", "renewal"])
@pytest.mark.parametrize("same_operator", [True, False], ids=["same_operator", "different_operator"])
def test_camera_entry_holding_vehicle_can_finish_during_monthly_collection(operation, same_operator):
    """Opposite schedule from cxvision_monthly_locking: entry owns vehicle first.

    The counter then owns operator and waits on that vehicle. Entry must still
    be able to take its implicit staff FK KEY SHARE and commit the admission.
    """
    with _isolated_checkout_postgres() as engine:
        _, plan, tokens = _seed(engine, 1)
        context = plan[0]
        vehicle_id, customer_id, staff_id, _ = _car_and_staff(engine, context, same_operator)
        today = business_now().date()
        original_id = None
        if operation == "renewal":
            with Session(engine) as db:
                original_id = _sell(db, vehicle_id, customer_id, staff_id, context["site"],
                    today - timedelta(days=31), today - timedelta(days=1), "EXPIRED-ENTRY-PERIOD").id
        observation_id = _observation(engine, context["camera"], context["site"], context["plate"], 0)
        entry_before_insert, exercised = Event(), []

        def hold_entry_before_insert(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("INSERT INTO PARKING_SESSIONS"):
                holder_pid = connection.scalar(text("SELECT pg_backend_pid()"))
                entry_before_insert.set()
                exercised.append(_wait_for_block(engine, holder_pid))

        def collect():
            assert entry_before_insert.wait(10), "Entry did not reach the session insert"
            with Session(engine) as db:
                start = today + timedelta(days=1)
                if operation == "sale":
                    return _sell(db, vehicle_id, customer_id, staff_id, context["site"],
                        start, start + timedelta(days=30), "FUTURE-ENTRY-PERIOD").id
                return monthly_service.renew_subscription(db, original_id, MonthlyPassRenew(
                    start_date=start, end_date=start + timedelta(days=30), price=100000,
                    payment_method="cash", site_id=context["site"], request_id="renew-final-entry-order",
                ), staff_id).id

        def camera():
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post(f"/api/v2/vision/observations/{observation_id}/process",
                    headers={"Authorization": f"Bearer {tokens[0]}"})
                return response.status_code, response.json()

        event.listen(engine, "before_cursor_execute", hold_entry_before_insert)
        try:
            with _pg_app(engine) as errors:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    counter, entry = pool.submit(collect), pool.submit(camera)
                    period_id = counter.result(timeout=20)
                    status, body = entry.result(timeout=20)
            assert exercised == [True], "Counter never waited on entry's vehicle"
            assert not errors, errors
            assert status == 200 and body["state"] == "entered", body
            with Session(engine) as db:
                assert db.get(MonthlyPass, period_id).is_active
                # A period sold for tomorrow cannot change today's billing.
                session = db.get(ParkingSession, body["session_id"])
                assert session.status == "active" and session.monthly_pass_id is None
        finally:
            event.remove(engine, "before_cursor_execute", hold_entry_before_insert)


def test_cash_shift_close_waits_for_monthly_collection(monkeypatch):
    """Cash serialization stays exclusive even with FK-compatible user locks."""
    with _isolated_checkout_postgres() as engine:
        _, plan, _ = _seed(engine, 1)
        context = plan[0]
        vehicle_id, customer_id, staff_id, _ = _car_and_staff(engine, context)
        with Session(engine) as db:
            shift = CashShiftService.open_shift(db, db.get(User, staff_id), site_id=context["site"])
            db.commit()
            shift_id = shift.id
        counter_locked, exercised = Event(), []
        real_lock = monthly_service._lock_vehicle

        def hold_counter(db, target):
            row = real_lock(db, target)
            holder_pid = db.scalar(text("SELECT pg_backend_pid()"))
            counter_locked.set()
            exercised.append(_wait_for_block(engine, holder_pid))
            return row

        monkeypatch.setattr(monthly_service, "_lock_vehicle", hold_counter)

        def collect():
            with Session(engine) as db:
                today = business_now().date()
                return _sell(db, vehicle_id, customer_id, staff_id, context["site"],
                    today, today + timedelta(days=30), "CLOSING-SHIFT-PERIOD").id

        def close():
            assert counter_locked.wait(10)
            with Session(engine) as db:
                result = CashShiftService.close_shift(db, shift_id, db.get(User, staff_id), counted_cash=100000)
                db.commit()
                return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            counter, closing = pool.submit(collect), pool.submit(close)
            period_id = counter.result(timeout=20)
            summary = closing.result(timeout=20)
        assert exercised == [True], "Closing the shift bypassed the counter's cash lock"
        assert summary["expected_cash"] == 100000 and summary["difference"] == 0
        with Session(engine) as db:
            assert db.get(CashShift, shift_id).status == "closed"
            receipt = db.scalar(select(Payment).where(Payment.source_type == "monthly_pass",
                Payment.source_id == str(period_id), Payment.kind == "receipt"))
            assert receipt.shift_id == shift_id and receipt.amount == 100000
