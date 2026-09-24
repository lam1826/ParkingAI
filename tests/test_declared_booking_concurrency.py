"""Actual file SQLite connections compete before the first write."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.clock import BUSINESS_TZ
from crud import parking_session as session_crud
from expansion import declared_bookings
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.simplified_customer_schemas import AdvanceBookingCreate
from models.parking_slot import ParkingSlot
from models.role import Role
from models.user import User
from test_expansion_sites_concurrency import store, race  # noqa: F401


def prepare(store):
    engine, factory, now, ids = store
    with factory() as db:
        role = Role(name='customer'); db.add(role); db.flush()
        users = [User(username=f'declared-customer-{index}', role_id=role.id, password_hash='unused', full_name='Test') for index in range(2)]
        db.add_all(users); db.commit()
        return [user.id for user in users], db.get(ParkingSlot, ids['slot']).vehicle_type_id


def action(store, user_id, kind, *, plate='51A-123.45', key='parallel-declared-booking-01'):
    _, factory, now, ids = store
    def run():
        with factory() as db:
            try:
                row = declared_bookings.create(db, db.get(User, user_id), AdvanceBookingCreate(site_id=ids['site'],
                    license_plate=plate, vehicle_type_id=kind, start_at=(now+timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ),
                    end_at=(now+timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id=key))
                db.commit()
                return 201, row.id
            except HTTPException as exc:
                db.rollback(); return exc.status_code, None
            except IntegrityError:
                db.rollback(); return 409, None
    return run


def test_customer_declaration_and_walkin_cannot_both_hold_one_slot(store):
    engine, factory, now, ids = store
    users, kind = prepare(store)
    def walkin():
        with factory() as db:
            claimed = session_crud.claim_parking_slot(db, ids['slot'], vehicle_id=ids['vehicles'][1], check_in_time=now)
            db.commit()
            return (201 if claimed else 409), None
    result = race(engine, [action(store, users[0], kind), walkin])
    assert sorted(row[0] for row in result) == [201, 409]
    with factory() as db:
        assert bool(db.get(ParkingSlot, ids['slot']).is_occupied) != bool(db.scalar(select(DeclaredParkingReservation.id)))


def test_same_request_parallel_is_one_declaration(store):
    engine, factory, _, _ = store
    users, kind = prepare(store)
    call = action(store, users[0], kind)
    result = race(engine, [call, call])
    assert [row[0] for row in result] == [201, 201]
    assert result[0][1] == result[1][1]
    with factory() as db:
        assert len(db.scalars(select(DeclaredParkingReservation)).all()) == 1


def test_different_customers_same_plate_cannot_take_two_slots(store):
    engine, factory, _, ids = store
    users, kind = prepare(store)
    with factory() as db:
        source = db.get(ParkingSlot, ids['slot'])
        db.add(ParkingSlot(zone_id=source.zone_id, vehicle_type_id=kind, slot_name='Parallel second'))
        db.commit()
    result = race(engine, [action(store, users[0], kind), action(store, users[1], kind, plate='51a12345')])
    assert sorted(row[0] for row in result) == [201, 409]
    with factory() as db:
        assert len(db.scalars(select(DeclaredParkingReservation)).all()) == 1
