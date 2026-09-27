"""Different plate typography must not create a second physical vehicle."""
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from expansion import portal_service
from expansion.portal_models import PortalAccountLink, PortalVehicleRequest
from models.vehicle import Vehicle
from models.parking_session import ParkingSession
from routers.vehicle import create_vehicle, update_vehicle
from schemas.vehicle import VehicleCreate, VehicleUpdate
from services.parking_service import ParkingService
from test_expansion_sites import env  # noqa: F401


def prepare(env):
    env.vehicle.license_plate = '30A-123.45'
    env.db.commit()
    return env.db.scalar(select(func.count()).select_from(Vehicle))


def request(env, customer_id):
    row = PortalVehicleRequest(customer_id=customer_id, license_plate='30A12345',
                               vehicle_type_id=env.vehicle.vehicle_type_id)
    env.db.add(row)
    env.db.commit()
    return row


def test_portal_approval_reuses_existing_vehicle_and_next_admission_works(env):
    before = prepare(env)
    row = request(env, env.customer.id)
    result = portal_service.resolve_vehicle(env.db, env.staff, row.id, True)
    assert result.status == 'approved'
    assert env.db.scalar(select(func.count()).select_from(Vehicle)) == before
    stay = ParkingService(env.db).check_in('30A12345', env.vehicle.vehicle_type_id,
                                          env.staff.id, parking_slot_id=env.slot.id)
    assert env.db.get(ParkingSession, stay['session_id']).vehicle_id == env.vehicle.id
    assert env.vehicle.license_plate == '30A-123.45'


def test_portal_approval_cannot_bypass_existing_owner_with_punctuation(env):
    before = prepare(env)
    other_customer = env.db.scalar(select(PortalAccountLink.customer_id).where(
        PortalAccountLink.user_id == env.stranger.id))
    row = request(env, other_customer)
    with pytest.raises(HTTPException) as error:
        portal_service.resolve_vehicle(env.db, env.staff, row.id, True)
    assert error.value.status_code == 409
    env.db.rollback()
    assert env.db.scalar(select(func.count()).select_from(Vehicle)) == before
    assert env.vehicle.customer_id == env.customer.id
    assert row.status == 'pending'


def test_portal_approval_refuses_ambiguous_legacy_identity(env):
    prepare(env)
    env.other.license_plate = '30A12345'
    env.db.commit()
    row = request(env, env.customer.id)
    with pytest.raises(HTTPException) as error:
        portal_service.resolve_vehicle(env.db, env.staff, row.id, True)
    assert error.value.status_code == 409


def test_catalog_create_rejects_formatting_duplicate(env):
    prepare(env)
    with pytest.raises(HTTPException) as error:
        create_vehicle(VehicleCreate(license_plate='30A12345',
            vehicle_type_id=env.vehicle.vehicle_type_id, customer_id=env.customer.id), env.db)
    assert error.value.status_code == 409


def test_catalog_update_rejects_other_vehicle_formatting_duplicate(env):
    prepare(env)
    with pytest.raises(HTTPException) as error:
        update_vehicle(env.other.id, VehicleUpdate(license_plate='30A12345'), env.db)
    assert error.value.status_code == 409


def test_catalog_can_reformat_same_vehicle_before_history(env):
    before = prepare(env)
    row = update_vehicle(env.vehicle.id, VehicleUpdate(license_plate='30A12345'), env.db)
    assert row.id == env.vehicle.id
    assert env.db.scalar(select(func.count()).select_from(Vehicle)) == before
