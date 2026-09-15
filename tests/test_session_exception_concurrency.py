"""True separate-connection races between cashiers and manager exceptions."""
from sqlalchemy import func, select

from models.parking_session_event import ParkingSessionEvent
from models.parking_session import ParkingSession
from models.payment import Payment
from models.price_config import PriceConfig
from models.role import Role
from models.user import User
from schemas.session_exception import PlateCorrectionRequest, SessionExceptionRequest
from services.session_exception_service import SessionExceptionService
from test_check_out_concurrency import env as race_env, _put_checkout


def manager_action(env, *, request_id="race-cancel", action="cancelled"):
    with env.Session() as db:
        role = db.scalar(select(Role).where(Role.name == "manager"))
        if role is None:
            role = Role(name="manager"); db.add(role); db.flush()
        db.get(User, env.staff_b).role = role
        db.commit()
    def execute():
        with env.Session() as db:
            body = (PlateCorrectionRequest(reason="Xác minh ngoại lệ tại cổng", request_id=request_id, license_plate="59A77777")
                    if action == "plate_corrected" else SessionExceptionRequest(reason="Xác minh ngoại lệ tại cổng", request_id=request_id))
            result = SessionExceptionService(db).apply(db.get(User, env.staff_b), None, env.session_id,
                body, action)
            return "OK", 200, result
    return execute


def test_cancellation_and_checkout_only_one_can_commit(race_env):
    cancel = manager_action(race_env)
    checkout = _put_checkout(race_env, race_env.staff_a)
    results = race_env.run_pair(cancel, checkout)
    assert sorted(row[1] for row in results) == [200, 409], results
    state = race_env.session_state(race_env.session_id)
    with race_env.Session() as db:
        events = db.scalar(select(func.count()).select_from(ParkingSessionEvent))
        payments = db.scalar(select(func.count()).select_from(Payment))
    if state["status"] == "cancelled":
        assert events == 1 and payments == 0 and state["fee"] is None
    else:
        assert state["status"] == "completed" and events == 0 and payments == 1 and state["fee"] > 0
    assert state["slot_occupied"] is False


def test_repeated_cancellation_has_one_immutable_event(race_env):
    cancel = manager_action(race_env)
    results = race_env.run_pair(cancel, cancel)
    assert [row[1] for row in results] == [200, 200], results
    assert results[0][2] == results[1][2]
    with race_env.Session() as db:
        assert db.scalar(select(func.count()).select_from(ParkingSessionEvent)) == 1
        assert db.scalar(select(func.count()).select_from(Payment)) == 0


def test_lost_ticket_race_does_not_double_charge_or_release_early(race_env):
    lost = manager_action(race_env, action="lost_ticket")
    checkout = _put_checkout(race_env, race_env.staff_a)
    results = race_env.run_pair(lost, checkout)
    assert results[1][1] == 200 and results[0][1] in {200, 409}, results
    state = race_env.session_state(race_env.session_id)
    assert state["status"] == "completed" and state["slot_occupied"] is False
    with race_env.Session() as db:
        assert db.scalar(select(func.count()).select_from(Payment)) == 1
        assert db.scalar(select(Payment.amount)) == state["fee"]


def test_correction_and_checkout_keep_exactly_one_live_or_paid_session(race_env):
    from core.billing import snapshot_values
    # The reusable race fixture models a pre-P1 stay. Replace its empty legacy
    # setup record before the test starts to exercise a genuine new admission.
    with race_env.Session() as db:
        old = db.get(ParkingSession, race_env.session_id)
        fields = {key: getattr(old, key) for key in ("id", "vehicle_id", "parking_slot_id", "check_in_time", "staff_in_id", "status")}
        db.delete(old); db.flush()
        db.add(ParkingSession(**fields, **snapshot_values(db.get(PriceConfig, race_env.price_id))))
        db.commit()
    correct = manager_action(race_env, action="plate_corrected")
    checkout = _put_checkout(race_env, race_env.staff_a)
    results = race_env.run_pair(correct, checkout)
    assert sorted(row[1] for row in results) == [200, 409], results
    state = race_env.session_state(race_env.session_id)
    with race_env.Session() as db:
        events = list(db.scalars(select(ParkingSessionEvent)))
        payments = list(db.scalars(select(Payment)))
        sessions = list(db.scalars(select(ParkingSession)))
    if state["status"] == "cancelled":
        assert len(events) == 1 and not payments and len(sessions) == 2
        assert sum(row.status == "active" for row in sessions) == 1
        assert state["slot_occupied"] is True
    else:
        assert state["status"] == "completed" and len(payments) == 1 and not events and len(sessions) == 1
        assert state["slot_occupied"] is False
