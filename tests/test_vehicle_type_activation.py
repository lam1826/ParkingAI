"""Inactive categories stop future service without rewriting historical stays."""
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from checkout_helpers import quote_confirmation
from core.clock import BUSINESS_TZ
from models.parking_session import ParkingSession
from models.vehicle_type import VehicleType
from test_core_crud_permissions import core_access  # noqa: F401


def type_url(context):
    return f"/api/v1/vehicle-types/{context['vehicle-types'].id}"


def admission(context, path):
    common = {"parking_slot_id": context["parking-slots"].id}
    if path == "id":
        return "/api/v1/parking-sessions/check-in", {**common, "vehicle_id": context["vehicles"].id}
    common.update(license_plate=context["vehicles"].license_plate, vehicle_type_id=context["vehicle-types"].id)
    return (f"/api/v2/sites/{context['site'].id}/check-in" if path == "scoped" else "/parking/check-in"), common


def test_manager_controls_activity_and_staff_reads_status(client, core_access):
    manager = core_access["headers"]["manager"]
    staff = core_access["headers"]["staff"]
    response = client.post("/api/v1/vehicle-types", headers=manager, json={"name": "Inactive test type", "is_active": False})
    assert response.status_code == 201 and response.json()["is_active"] is False
    url = f"/api/v1/vehicle-types/{response.json()['id']}"
    assert client.get(url, headers=staff).json()["is_active"] is False
    assert client.put(url, headers=staff, json={"is_active": True}).status_code == 403
    assert client.put(url, headers=manager, json={"is_active": None}).status_code == 422
    assert client.put(url, headers=manager, json={"is_active": True}).json()["is_active"] is True


@pytest.mark.parametrize("path", ["plate", "id", "scoped"])
def test_inactive_type_blocks_every_admission_and_reactivation_restores_it(client, db_session, core_access, path):
    manager = core_access["headers"]["manager"]
    staff = core_access["headers"]["staff"]
    assert client.put(type_url(core_access), headers=manager, json={"is_active": False}).status_code == 200
    url, body = admission(core_access, path)
    response = client.post(url, headers=staff, json=body)
    assert response.status_code == 409, response.text
    assert "ngừng" in response.json()["detail"]
    assert db_session.query(ParkingSession).count() == 0
    db_session.refresh(core_access["parking-slots"])
    assert core_access["parking-slots"].is_occupied is False
    assert client.put(type_url(core_access), headers=manager, json={"is_active": True}).status_code == 200
    response = client.post(url, headers=staff, json=body)
    assert response.status_code == 201, response.text
    assert db_session.query(ParkingSession).count() == 1


def test_deactivation_requires_departure_preserves_history_and_can_reactivate(client, db_session, core_access):
    staff, manager = (core_access["headers"][name] for name in ("staff", "manager"))
    url, body = admission(core_access, "scoped")
    assert client.post(url, headers=staff, json=body).status_code == 201
    session = db_session.scalar(select(ParkingSession))
    original_id = session.id
    assert client.put(type_url(core_access), headers=manager, json={"is_active": False}).status_code == 409
    db_session.refresh(core_access["vehicle-types"])
    assert core_access["vehicle-types"].is_active is True
    confirmation = quote_confirmation(client, staff, session.id)
    departed = client.put(f"/api/v1/parking-sessions/{session.id}/check-out", headers=staff, json=confirmation)
    assert departed.status_code == 200, departed.text
    completed = departed.json()
    assert client.put(type_url(core_access), headers=manager, json={"is_active": False}).status_code == 200
    assert client.delete(type_url(core_access), headers=manager).status_code == 409
    preserved = client.get(f"/api/v1/parking-sessions/{original_id}", headers=staff).json()
    assert preserved == completed
    assert client.put(type_url(core_access), headers=manager, json={"is_active": True}).status_code == 200


def test_existing_stay_can_exit_if_imported_type_is_already_inactive(client, db_session, core_access):
    staff = core_access["headers"]["staff"]
    url, body = admission(core_access, "plate")
    assert client.post(url, headers=staff, json=body).status_code == 201
    session = db_session.scalar(select(ParkingSession))
    # Represents older imported data. No endpoint may strand an existing stay
    # just because its historical category was disabled outside this workflow.
    db_session.execute(update(VehicleType).where(VehicleType.id == core_access["vehicle-types"].id).values(is_active=False))
    db_session.commit()
    confirmation = quote_confirmation(client, staff, session.id)
    result = client.post("/parking/check-out", headers=staff,
                         json={"license_plate": core_access["vehicles"].license_plate, **confirmation})
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed"


def test_availability_excludes_inactive_type_but_keeps_physical_inventory(client, core_access):
    manager = core_access["headers"]["manager"]
    staff = core_access["headers"]["staff"]
    url = f"/api/v2/sites/{core_access['site'].id}/availability"
    before = client.get(url, headers=staff).json()
    assert before["capacity_total"] == before["total"] == 1
    assert before["inactive_slots"] == 0
    assert client.put(type_url(core_access), headers=manager, json={"is_active": False}).status_code == 200
    after = client.get(url, headers=staff).json()
    assert after["capacity_total"] == after["inactive_slots"] == 1
    assert after["total"] == after["available_now"] == 0
    assert after["slots"] == []
    assert client.get("/parking/available-slots", headers=staff).json()["total_available"] == 0
    assert client.get("/api/v2/catalog/vehicle-types", headers=staff).json()["items"] == []


def test_type_with_live_reservation_cannot_be_deactivated(client, db_session, core_access, business_reference_now):
    from expansion.site_models import ParkingReservation
    staff, manager = (core_access["headers"][name] for name in ("staff", "manager"))
    vehicle = core_access["vehicles"]
    vehicle.customer_id = core_access["customers"].id
    db_session.commit()
    payload = {"site_id": core_access["site"].id, "vehicle_id": vehicle.id, "slot_id": core_access["parking-slots"].id,
               "start_at": (business_reference_now + timedelta(hours=1)).replace(tzinfo=BUSINESS_TZ).isoformat(),
               "end_at": (business_reference_now + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ).isoformat(),
               "request_id": "inactive-type-booking-example"}
    reservation = client.post(f"/api/v2/sites/{core_access['site'].id}/reservations", headers=staff, json=payload)
    assert reservation.status_code == 201, reservation.text
    assert client.put(type_url(core_access), headers=manager, json={"is_active": False}).status_code == 409
    assert db_session.query(ParkingReservation).count() == 1
    cancelled = client.post(f"/api/v2/sites/{core_access['site'].id}/reservations/{reservation.json()['id']}/cancel", headers=staff)
    assert cancelled.status_code == 200
    assert client.put(type_url(core_access), headers=manager, json={"is_active": False}).status_code == 200
    payload["request_id"] = "inactive-type-booking-forbidden"
    blocked = client.post(f"/api/v2/sites/{core_access['site'].id}/reservations", headers=staff, json=payload)
    assert blocked.status_code == 409
    assert db_session.query(ParkingReservation).count() == 1
