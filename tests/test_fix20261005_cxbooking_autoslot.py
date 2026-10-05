from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_expansion_sites import env, data, reserve  # noqa
from test_portal_api import portal  # noqa
from test_timed_parking import timed, purchase  # noqa

from models.parking_slot import ParkingSlot
from models.parking_session import ParkingSession
from models.vehicle import Vehicle
from models.zone import Zone
from database import get_db
from services.auth_service import get_current_user
from expansion.site_router import router as site_router
from expansion.timed_parking_models import TimedParkingPass
from sqlalchemy import select, func




def test_staff_reservation_on_higher_slot(env):
    # Second slot of same type in same zone/site, higher id
    slot2 = ParkingSlot(slot_name="A-02", zone_id=env.slot.zone_id, vehicle_type_id=env.slot.vehicle_type_id,
                        is_active=True, is_occupied=False)
    env.db.add(slot2)
    env.db.commit()
    assert slot2.id > env.slot.id
    row = reserve(env, slot=slot2)  # staff reservation starting now for env.vehicle
    print("\nreservation slot:", row.slot_id, "status:", row.status, "start:", row.start_at, "now:", env.now)

    avail = env.client.get(f"/api/v2/sites/{env.a.id}/availability")
    assert avail.status_code == 200, avail.text
    slots = avail.json()["slots"]
    print("picker candidates (available_now==True):", [s["slot_name"] for s in slots if s["available_now"] is True])
    print("reserved slot row:", [s for s in slots if s["id"] == slot2.id])

    body = {"license_plate": env.vehicle.license_plate, "vehicle_type_id": env.slot.vehicle_type_id}
    auto = env.client.post(f"/api/v2/sites/{env.a.id}/check-in", json=body)
    print("auto-slot (UI default) check-in:", auto.status_code, auto.json())
    assert auto.status_code == 201, auto.text
    assert auto.json()["slot_name"] == "A-02"


def test_prepaid_ticket_after_walkin_left(timed, monkeypatch):
    from services.parking_service import ParkingService
    from services.checkout_service import CheckoutService
    from schemas.checkout import CheckoutConfirmation
    context, body, slot, rate = timed
    client, current, users, site, kind, db = context
    # Second slot in the same zone (higher id)
    db.get(Zone, slot.zone_id).capacity = 2
    t2 = ParkingSlot(slot_name="T-2", zone_id=slot.zone_id, vehicle_type_id=kind.id, is_active=True, is_occupied=False)
    db.add(t2)
    db.commit()
    # A walk-in car is parked in T-1 when the customer buys the ticket
    walkin = ParkingService(db).check_in("51F-111.22", kind.id, users[0].id, _expected_site_id=site.id)
    print("\nwalk-in placed in:", walkin.get("slot_name"))
    order = purchase(timed)
    ticket = db.get(TimedParkingPass, order["timed_pass_id"])
    print("ticket slot:", db.get(ParkingSlot, ticket.slot_id).slot_name, "start:", ticket.start_at)
    assert ticket.slot_id == t2.id
    # Walk-in leaves before the ticket starts
    leave_at = ticket.start_at - timedelta(seconds=30)
    monkeypatch.setattr("crud.parking_session.server_now", lambda: leave_at)
    service = CheckoutService(db)
    quote = service.quote(walkin["session_id"], users[0].id)
    done = service.confirm(CheckoutConfirmation(quote_token=quote["quote_token"], payment_confirmed=True,
        payment_method="transfer" if quote["parking_fee"] else None), users[0].id, session_id=walkin["session_id"])
    assert done.status == "completed"
    db.refresh(slot)
    print("T-1 occupied after walk-in exit:", slot.is_occupied)

    # Customer arrives at the ticket start; staff uses default "He thong xep cho" via the real site router
    monkeypatch.setattr("crud.parking_session.server_now", lambda: ticket.start_at)
    app = FastAPI()
    app.include_router(site_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: users[0]
    staff = TestClient(app)
    avail = staff.get(f"/api/v2/sites/{site.id}/availability").json()["slots"]
    print("picker candidates:", [s["slot_name"] for s in avail if s["available_now"] is True],
          "| T-2 row:", [s for s in avail if s["id"] == t2.id])
    vehicle = db.get(Vehicle, body["vehicle_id"])
    req = {"license_plate": vehicle.license_plate, "vehicle_type_id": kind.id}
    auto = staff.post(f"/api/v2/sites/{site.id}/check-in", json=req)
    print("auto-slot (UI default) check-in:", auto.status_code, auto.json())
    assert auto.status_code == 201, auto.text
    assert auto.json()["slot_name"] == "T-2"


def test_automatic_placement_prefers_current_allocation_on_higher_slot(env):
    from expansion import reservations
    second = ParkingSlot(slot_name='A-02', zone_id=env.slot.zone_id,
                         vehicle_type_id=env.vehicle.vehicle_type_id)
    env.db.add(second)
    env.db.commit()
    allocation = reservations.reserve(env.db, env.staff, data(env, slot=second), allocation=True)
    env.db.commit()
    response = env.client.post(f'/api/v2/sites/{env.a.id}/check-in', json={
        'license_plate':env.vehicle.license_plate, 'vehicle_type_id':env.vehicle.vehicle_type_id})
    assert response.status_code == 201, response.text
    assert response.json()['slot_name'] == second.slot_name
    assert allocation.status == 'active'
    env.db.refresh(env.slot)
    assert env.slot.is_occupied is False
