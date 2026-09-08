"""Independent acceptance checks for object authorization boundaries."""
from datetime import timedelta
from uuid import uuid4

import pytest

from core.clock import business_now
from expansion.site_models import ParkingReservation, ParkingSite
from expansion.vision_models import VisionObservation
from test_expansion_vision_api import picture, vision  # noqa: F401
from test_expansion_sites import env, data  # noqa: F401
from test_review2_regressions import _transfer_vehicle
from expansion import reservations
from expansion.site_schemas import AllocationCreate
from fastapi import HTTPException


@pytest.mark.parametrize("site_active", [True, False], ids=["active-site", "closed-site"])
def test_foreign_observation_response_matches_missing_object_including_body(vision, site_active):
    client, db, _, foreign, _ = vision
    now = business_now()
    row = VisionObservation(camera_id=foreign.id, site_id=foreign.site_id, event_id=str(uuid4()),
        image_hash="0" * 64, image_bytes=picture(), image_width=180, image_height=80,
        observed_at=now, captured_at=now, expires_at=now + timedelta(hours=1),
        ocr_status="unavailable", engine="disabled")
    db.add(row)
    db.commit()
    db.get(ParkingSite, foreign.site_id).is_active = site_active
    db.commit()
    for action, method, body in (("/image", "GET", None),
                                 ("/review", "POST", {"decision": "reject"}),
                                 ("", "DELETE", None)):
        outside = client.request(method, f"/api/v2/vision/observations/{row.id}{action}", json=body)
        missing = client.request(method, f"/api/v2/vision/observations/{uuid4()}{action}", json=body)
        assert outside.status_code == missing.status_code == 404
        assert outside.json() == missing.json()
    assert db.get(VisionObservation, row.id).review_status == "pending"


def test_new_owner_cannot_consume_previous_owners_dedicated_allocation(env):
    original_customer_id = env.vehicle.customer_id
    body = data(env)
    allocation = reservations.reserve(env.db, env.staff, AllocationCreate(**body.model_dump()), allocation=True)
    env.db.commit()
    new_customer_id = _transfer_vehicle(env)
    assert new_customer_id != original_customer_id
    # A transferred vehicle cannot enter using the former owner's allocation.
    assert not reservations.admission_allowed(env.db, env.slot.id, vehicle_id=env.vehicle.id, at=env.now, lock=False)
    # Creating a customer booking must not become a way to acquire that entitlement.
    with pytest.raises(HTTPException) as error:
        reservations.reserve(env.db, env.stranger,
            body.model_copy(update={"request_id": "new-owner-allocation-0001"}), customer=True)
    assert error.value.status_code == 409
    env.db.rollback()
    assert allocation.customer_id == original_customer_id
    reservations.cancel(env.db, env.staff, allocation)
    env.db.commit()
    row = reservations.reserve(env.db, env.stranger,
        body.model_copy(update={"request_id": "new-owner-allocation-0001"}), customer=True)
    env.db.commit()
    assert row.customer_id == new_customer_id and row.status == "confirmed"


def test_same_owner_reservation_can_consume_dedicated_allocation(env):
    body = data(env)
    allocation = reservations.reserve(env.db, env.staff, AllocationCreate(**body.model_dump()), allocation=True)
    env.db.commit()
    row = reservations.reserve(env.db, env.account,
        body.model_copy(update={"request_id": "same-owner-allocation-0001"}), customer=True)
    env.db.commit()
    assert row.customer_id == allocation.customer_id
    assert reservations.admission_allowed(env.db, env.slot.id, vehicle_id=env.vehicle.id, at=env.now)
    arrived = reservations.arrive(env.db, env.staff, row)
    env.db.commit()
    assert arrived.status == "arrived"


def test_legacy_booking_cannot_bypass_previous_owners_allocation_at_admission(env):
    body = data(env)
    reservations.reserve(env.db, env.staff, AllocationCreate(**body.model_dump()), allocation=True)
    env.db.commit()
    new_customer_id = _transfer_vehicle(env)
    # This row is a fixture of the formerly permitted reservation path. Admission
    # must stay safe for databases which already contain such a booking.
    row = ParkingReservation(site_id=env.a.id, slot_id=env.slot.id, customer_id=new_customer_id,
        vehicle_id=env.vehicle.id, start_at=env.now, end_at=env.now + timedelta(hours=2),
        arrival_deadline=env.now + timedelta(minutes=15), request_id="legacy-cross-owner-allocation",
        created_by_id=env.stranger.id)
    env.db.add(row)
    env.db.commit()
    assert not reservations.admission_allowed(env.db, env.slot.id, vehicle_id=env.vehicle.id, at=env.now, lock=False)
    with pytest.raises(HTTPException) as error:
        reservations.arrive(env.db, env.staff, row)
    assert error.value.status_code == 409
    env.db.rollback()
    assert row.status == "confirmed" and not env.slot.is_occupied


def test_owner_transfer_before_reservation_first_write_rolls_back_stale_authority(env, tmp_path):
    """Separate SQLite connections: transfer commits after authorization, before lock.

    The insert guard must reject a customer snapshot read before the transfer,
    even though SQLAlchemy still has the old Vehicle in its identity map.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import create_engine, event, func, select
    from sqlalchemy.orm import sessionmaker

    from expansion.portal_models import PortalAccountLink
    from expansion.site_router import _save
    from models.user import User
    from models.vehicle import Vehicle
    from routers.vehicle import update_vehicle
    from schemas.vehicle import VehicleUpdate

    body = data(env)
    actor_id, vehicle_id = env.account.id, env.vehicle.id
    new_customer_id = env.db.scalar(select(PortalAccountLink.customer_id).where(
        PortalAccountLink.user_id == env.stranger.id))
    env.db.commit()
    engine = create_engine("sqlite:///" + (tmp_path / "owner-transfer-race.sqlite").as_posix(),
        connect_args={"check_same_thread": False, "timeout": 15})
    source, target = env.db.get_bind().raw_connection(), engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    reached_first_write, transfer_committed = threading.Event(), threading.Event()

    def pause_first_booking_write(connection, cursor, statement, parameters, context, many):
        if (threading.current_thread().name.startswith("reservation-authority")
                and statement.lstrip().upper().startswith(("UPDATE CUSTOMERS", "UPDATE VEHICLES"))
                and not reached_first_write.is_set()):
            reached_first_write.set()
            assert transfer_committed.wait(timeout=10), "Transfer did not commit in time"

    def book():
        with factory() as db:
            actor = db.get(User, actor_id)
            try:
                _save(db, lambda: reservations.reserve(db, actor, body, customer=True))
                return 201
            except HTTPException as error:
                return error.status_code

    event.listen(engine, "before_cursor_execute", pause_first_booking_write)
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="reservation-authority") as pool:
            future = pool.submit(book)
            try:
                assert reached_first_write.wait(timeout=10), "Booking did not reach first write"
                with factory() as db:
                    # This is the real handler used by authorized legacy vehicle
                    # updates, including its relation checks and database guards.
                    result = update_vehicle(vehicle_id, VehicleUpdate(customer_id=new_customer_id), db)
                    assert result.customer_id == new_customer_id
            finally:
                transfer_committed.set()
            # After waiting, refreshed ownership is denied (404) before insert;
            # an older implementation may reach the database backstop (409).
            assert future.result(timeout=20) in {404, 409}
        with factory() as db:
            assert db.get(Vehicle, vehicle_id).customer_id == new_customer_id
            assert db.scalar(select(func.count()).select_from(ParkingReservation)) == 0
    finally:
        event.remove(engine, "before_cursor_execute", pause_first_booking_write)
        engine.dispose()
