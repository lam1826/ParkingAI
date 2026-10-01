"""An arrival must not admit a different identity after waiting for a lock."""
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update

from core import vehicle_identity
from expansion import reservations
from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from test_expansion_sites import env, reserve  # noqa: F401


@pytest.mark.parametrize('same_identity', [False, True])
def test_arrival_rechecks_vehicle_identity_after_lock_wait(env, monkeypatch, same_identity):
    row = reserve(env)
    previous_plate = env.vehicle.license_plate
    changed_plate = vehicle_identity.canonical_identity(previous_plate) if same_identity else '30A-123.45'
    original_lock = vehicle_identity.lock_identity
    changed = False

    def edit_during_wait(db, type_id, plate):
        nonlocal changed
        original_lock(db, type_id, plate)
        if not changed:
            # Inject the final state of a vehicle edit while the request was
            # waiting, using a real DB write rather than changing its ORM cache.
            changed = True
            db.execute(update(Vehicle).where(Vehicle.id == env.vehicle.id)
                       .values(license_plate=changed_plate))

    monkeypatch.setattr(vehicle_identity, 'lock_identity', edit_during_wait)
    if same_identity:
        arrived = reservations.arrive(env.db, env.staff, row)
        env.db.commit()
        assert arrived.status == 'arrived'
        assert env.db.get(ParkingSession, arrived.session_id).vehicle_id == env.vehicle.id
        assert env.db.scalar(select(func.count()).select_from(Vehicle)) == 2
    else:
        with pytest.raises(HTTPException) as error:
            reservations.arrive(env.db, env.staff, row)
        assert error.value.status_code == 409
        assert 'Thông tin xe vừa thay đổi' in error.value.detail
        assert env.db.scalar(select(func.count()).select_from(ParkingSession)) == 0
        env.db.refresh(row)
        assert row.status == 'confirmed' and row.session_id is None
