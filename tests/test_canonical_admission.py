"""Formatting variants share one admission identity; legacy ambiguity fails closed."""
from sqlalchemy import select

from core.vehicle_identity import canonical_identity
from models.vehicle import Vehicle
from models.parking_session import ParkingSession
from services.parking_service import ParkingService
from fastapi import HTTPException
import pytest

from test_check_in_concurrency import env, service_check_in  # noqa: F401


def test_admission_reuses_stored_identity_without_rewriting_history(env):
    identity = env.ensure_vehicle('51A-112.23')
    with env.Session() as db:
        response = ParkingService(db).check_in('51a11223', env.vt_id, env.user_id)
        assert response['license_plate'] == '51A-112.23'
        assert db.get(ParkingSession, response['session_id']).vehicle_id == identity
        assert len(db.scalars(select(Vehicle)).all()) == 1


def test_ambiguous_legacy_variants_reject_even_an_exact_match(env):
    env.ensure_vehicle('51A-112.23')
    env.ensure_vehicle('51A11223')
    with env.Session() as db:
        before = [row.license_plate for row in db.scalars(select(Vehicle))]
        with pytest.raises(HTTPException) as exc:
            ParkingService(db).check_in('51A11223', env.vt_id, env.user_id)
        assert exc.value.status_code == 409
        assert [row.license_plate for row in db.scalars(select(Vehicle))] == before
        assert db.scalar(select(ParkingSession.id)) is None


def test_two_formatting_variants_concurrently_create_only_one_vehicle_and_stay(env):
    results = env.run_pair(service_check_in, ('51A-112.23', None), ('51a11223', None))
    assert sum(row[1] == 201 for row in results) == 1, results
    assert all(row[1] in {201, 400, 409} for row in results), results
    summary = env.audit()
    assert summary['active_total'] == summary['vehicles'] == 1
