"""Reserved arrival and direct admission share the PostgreSQL identity lock."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from core import vehicle_identity
from core.clock import BUSINESS_TZ, business_now
from expansion import reservations
from expansion.site_models import ParkingReservation, ParkingSite
from expansion.site_schemas import ReservationCreate
from models import Customer, ParkingSession, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone
from services.parking_service import ParkingService
from test_postgres_integration import POSTGRES_TEST_URL, _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason='Requires isolated PostgreSQL service')


@pytest.mark.parametrize('first', ['entry', 'arrival'])
def test_reserved_arrival_and_direct_entry_serialize_without_deadlock(monkeypatch, first):
    """Pause the winner while holding identity; the loser must not hold rows.

    Uses two real transactions and actual admission services. Scheduling only
    the identity seam reproduces the old vehicle/advisory lock cycle, without
    replacing either PostgreSQL lock or service with a mock implementation.
    """
    now = business_now().replace(microsecond=0)
    monkeypatch.setattr('crud.parking_session.server_now', lambda: now)
    with _isolated_checkout_postgres() as engine:
        with Session(engine) as db:
            role, kind, site = Role(name='admin'), VehicleType(name='Arrival car'), ParkingSite(name='Arrival lot')
            owner = Customer(full_name='Arrival owner', phone_number='PG-ARRIVAL-OWNER')
            db.add_all([role, kind, site, owner])
            db.flush()
            actor = User(username='arrival-admin', password_hash='unused', full_name='Operator', role_id=role.id)
            zone = Zone(name='Arrival zone', site_id=site.id, capacity=1)
            vehicle = Vehicle(license_plate='30A-123.45', vehicle_type_id=kind.id, customer_id=owner.id)
            db.add_all([actor, zone, vehicle])
            db.flush()
            slot = ParkingSlot(slot_name='ARRIVAL-1', vehicle_type_id=kind.id, zone_id=zone.id)
            db.add_all([slot, PriceConfig(vehicle_type_id=kind.id, ticket_type='HOURLY', price=10000,
                                          effective_date=now.date())])
            db.flush()
            booking = reservations.reserve(db, actor, ReservationCreate(site_id=site.id,
                slot_id=slot.id, vehicle_id=vehicle.id, start_at=now.replace(tzinfo=BUSINESS_TZ),
                end_at=(now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id=uuid4().hex))
            db.commit()
            actor_id, kind_id, slot_id, site_id, booking_id = actor.id, kind.id, slot.id, site.id, booking.id

        first_locked, second_waiting = Event(), Event()
        real_lock = vehicle_identity.lock_identity
        failures = []

        def scheduled_lock(db, type_id, plate):
            if db.info.get('operation') != first:
                second_waiting.set()
            real_lock(db, type_id, plate)
            if db.info.get('operation') == first and not first_locked.is_set():
                first_locked.set()
                assert second_waiting.wait(10), 'Second operation did not request identity'

        monkeypatch.setattr(vehicle_identity, 'lock_identity', scheduled_lock)

        def collect_error(context):
            error = context.original_exception
            failures.append((type(error).__name__, getattr(error, 'sqlstate', None)))

        def perform(operation):
            if operation != first:
                assert first_locked.wait(10), 'First operation did not acquire identity'
            with Session(engine, info={'operation': operation}) as db:
                try:
                    if operation == 'entry':
                        result = ParkingService(db).check_in('30A12345', kind_id, actor_id,
                            parking_slot_id=slot_id, _expected_site_id=site_id)
                        identity = result['session_id']
                    else:
                        row = reservations.arrive(db, db.get(User, actor_id), db.get(ParkingReservation, booking_id))
                        db.commit()
                        identity = row.session_id
                    return operation, 201, identity
                except HTTPException as error:
                    db.rollback()
                    return operation, error.status_code, str(error.detail)

        event.listen(engine, 'handle_error', collect_error)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                tasks = [workers.submit(perform, operation) for operation in ('entry', 'arrival')]
                outcomes = [task.result(timeout=25) for task in tasks]
        finally:
            event.remove(engine, 'handle_error', collect_error)
        assert not failures, failures
        assert outcomes[1][1] == 201, outcomes
        if first == 'entry':
            assert outcomes[0][1:] == outcomes[1][1:], outcomes
        else:
            # Direct entry's existing duplicate-stay contract is HTTP 400.
            assert outcomes[0][1] == 400, outcomes
            assert outcomes[0][2] == 'Xe đang ở trong bãi.'
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(ParkingSession)) == 1
            stay = db.scalar(select(ParkingSession))
            booking = db.get(ParkingReservation, booking_id)
            assert booking.status == 'arrived' and booking.session_id == stay.id == outcomes[1][2]
            assert db.get(ParkingSlot, slot_id).is_occupied
