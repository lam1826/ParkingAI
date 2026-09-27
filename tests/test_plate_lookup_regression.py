"""Plate lookup across human formatting variants, using disposable test data."""
import pytest
from sqlalchemy import select

from models.role import Role
from services.parking_service import ParkingService
from test_expansion_sites import env  # noqa: F401
from test_simplified_customer_flows import customer_env, admit, lookup  # noqa: F401


@pytest.mark.parametrize("role_name", ["admin", "manager"])
@pytest.mark.parametrize("query", ["30A-123.45", "30a12345", "30A 12345", " 30a-123.45 "])
def test_operational_lookup_matches_same_plate_across_formatting(env, role_name, query):
    env.vehicle.license_plate = "30A-123.45"
    if role_name == "admin":
        role = env.db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name)
            env.db.add(role)
            env.db.flush()
        env.staff.role = role
    env.db.commit()
    stay = ParkingService(env.db).check_in(
        env.vehicle.license_plate, env.vehicle.vehicle_type_id,
        env.staff.id, parking_slot_id=env.slot.id,
    )
    response = env.client.get(
        f"/api/v2/sites/{env.a.id}/sessions",
        params={"license_plate": query, "status": "active", "limit": 25, "offset": 0},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1, "A plate already parked must be found regardless of punctuation/case."
    assert response.json()[0]["id"] == stay["session_id"]


def test_normalized_lookup_remains_exact_and_site_scoped(env):
    env.vehicle.license_plate = "30A-123.45"
    env.db.commit()
    ParkingService(env.db).check_in(env.vehicle.license_plate, env.vehicle.vehicle_type_id,
                                  env.staff.id, parking_slot_id=env.slot.id)
    query = {"license_plate": "30a12345", "status": "active"}
    assert len(env.client.get(f"/api/v2/sites/{env.a.id}/sessions", params=query).json()) == 1
    assert env.client.get(f"/api/v2/sites/{env.b.id}/sessions", params=query).status_code == 403
    for plate in ["30A1234", "30A12346"]:
        response = env.client.get(f"/api/v2/sites/{env.a.id}/sessions", params={**query, "license_plate": plate})
        assert response.status_code == 200 and response.json() == []


@pytest.mark.parametrize("query", ["30A-123.45", "30a12345", "30A 12345", " 30a-123.45 "])
def test_customer_owned_lookup_accepts_formatting_without_exposing_other_customers(customer_env, query):
    e = customer_env
    e.vehicle.license_plate = "30A-123.45"
    e.db.commit()
    stay = admit(e, e.vehicle.license_plate)
    e.actor["user"] = e.account
    response = lookup(e, query)
    assert response.status_code == 200, response.text
    assert response.json()["session"]["id"] == stay["session_id"]
    assert response.json()["access"]["kind"] == "owned"
    assert lookup(e, query, site_id=e.b.id).status_code == 404
    e.actor["user"] = e.stranger
    denied = lookup(e, query)
    absent = lookup(e, "30A99999")
    assert denied.status_code == absent.status_code == 404
    assert denied.json() == absent.json()
