"""Separate connections contend at the first write, rather than an in-memory fake race."""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from core.clock import BUSINESS_TZ, business_now
from crud import parking_session as session_crud
from database import Base
from expansion import reservations
from expansion.site_models import ParkingReservation, ParkingSite, SiteMembership
from expansion.site_schemas import ReservationCreate
from models.customer import Customer
from models.parking_slot import ParkingSlot
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.zone import Zone


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'site-race.db').as_posix()}",
                           connect_args={"check_same_thread": False, "timeout": 20})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = business_now().replace(microsecond=0)
    monkeypatch.setattr(session_crud, "server_now", lambda: now)
    with factory() as db:
        role, site = Role(name="manager"), ParkingSite(name="Race site")
        customer, kind = Customer(full_name="Race", phone_number="0919999888"), VehicleType(name="Race car")
        db.add_all([role, site, customer, kind])
        db.flush()
        actor = User(username="site-race", role_id=role.id, password_hash="unused", full_name="Race")
        zone = Zone(name="Race zone", site_id=site.id, capacity=3)
        db.add_all([actor, zone])
        db.flush()
        db.add(SiteMembership(site_id=site.id, user_id=actor.id, role="manager"))
        slot = ParkingSlot(zone_id=zone.id, vehicle_type_id=kind.id, slot_name="Race 1")
        vehicles = [Vehicle(license_plate=f"51X0000{i}", vehicle_type_id=kind.id, customer_id=customer.id) for i in (1, 2)]
        db.add_all([slot, *vehicles])
        db.commit()
        ids = {"actor": actor.id, "site": site.id, "slot": slot.id, "vehicles": [v.id for v in vehicles]}
    yield engine, factory, now, ids
    engine.dispose()


def race(engine, actions):
    barrier = threading.Barrier(2, timeout=10)
    visited = threading.local()
    def first_write(conn, cursor, statement, params, context, many):
        if statement.lstrip().upper().startswith("UPDATE ") and not getattr(visited, "done", False):
            visited.done = True
            barrier.wait()
    event.listen(engine, "before_cursor_execute", first_write)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(action) for action in actions]
            return [future.result(timeout=30) for future in futures]
    finally:
        event.remove(engine, "before_cursor_execute", first_write)


def book_action(store, vehicle_index, request_id):
    engine, factory, now, ids = store
    def action():
        with factory() as db:
            actor = db.get(User, ids["actor"])
            body = ReservationCreate(site_id=ids["site"], slot_id=ids["slot"], vehicle_id=ids["vehicles"][vehicle_index],
                                     start_at=(now + timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ),
                                     end_at=(now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id=request_id)
            try:
                row = reservations.reserve(db, actor, body)
                db.commit()
                return 201, row.id
            except HTTPException as exc:
                db.rollback()
                return exc.status_code, None
    return action


def test_two_customers_cannot_book_same_slot_interval(store):
    engine, factory, _, _ = store
    results = race(engine, [book_action(store, 0, "race-book-request-0001"), book_action(store, 1, "race-book-request-0002")])
    assert sorted(result[0] for result in results) == [201, 409]
    with factory() as db:
        assert len(db.scalars(select(ParkingReservation)).all()) == 1


def test_same_request_parallel_retry_has_one_booking(store):
    engine, factory, _, _ = store
    action = book_action(store, 0, "race-retry-request-0001")
    results = race(engine, [action, action])
    assert results[0][0] == results[1][0] == 201
    assert results[0][1] == results[1][1]


def test_walk_in_and_future_booking_cannot_both_claim_capacity(store):
    engine, factory, now, ids = store
    def walk_in():
        with factory() as db:
            claimed = session_crud.claim_parking_slot(db, ids["slot"], vehicle_id=ids["vehicles"][1], check_in_time=now)
            db.commit()
            return (201 if claimed else 409), None
    results = race(engine, [book_action(store, 0, "race-walkin-request-0001"), walk_in])
    assert sorted(result[0] for result in results) == [201, 409]
    with factory() as db:
        slot = db.get(ParkingSlot, ids["slot"])
        bookings = db.scalars(select(ParkingReservation)).all()
        assert bool(slot.is_occupied) != bool(bookings)

