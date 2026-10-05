from datetime import timedelta

import pytest
from sqlalchemy import select, func

from core.clock import BUSINESS_TZ, business_now
from expansion.portal_models import PortalOrder, PortalPaymentEvent
from expansion.portal_service import process_event
from expansion.portal_worker import run_portal_maintenance
from expansion.simplified_customer_router import router as declared_router
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.timed_parking_models import ParkingCapacityHold, TimedParkingPass
from models.parking_slot import ParkingSlot
from models.payment import Payment
from models.vehicle import Vehicle
from models.zone import Zone
from test_portal_api import portal, onboard, advance_past_order_deadline  # noqa: F401
from test_timed_parking import timed  # noqa: F401


def _second_slot(db, slot, kind):
    db.get(Zone, slot.zone_id).capacity = 2
    db.flush()
    db.add(ParkingSlot(slot_name="T-2", zone_id=slot.zone_id, vehicle_type_id=kind.id, is_active=True, is_occupied=False))
    db.commit()


@pytest.mark.parametrize("declarer", ["owner", "stranger"])
def test_demo_paid_order_unfulfillable_after_declared_booking(timed, declarer, monkeypatch):
    portal_, body, slot, rate = timed
    client, current, users, site, kind, db = portal_
    client.app.include_router(declared_router, prefix="/api/v2")
    _second_slot(db, slot, kind)
    resp = client.post("/api/v2/me/orders", json=body)
    assert resp.status_code == 200, resp.text
    order = resp.json()
    print(f"\n[{declarer}] order", order["status"], "slot", order["slot"]["name"], "hold_expires", order["hold_expires_at"])
    vehicle = db.get(Vehicle, body["vehicle_id"])
    if declarer == "stranger":
        current["user"] = users[2]
    booking = client.post("/api/v2/me/advance-bookings", json={"site_id": site.id, "license_plate": vehicle.license_plate,
        "vehicle_type_id": kind.id, "start_at": order["start_at"], "end_at": order["end_at"],
        "request_id": f"declared-during-hold-{declarer}"})
    print(f"[{declarer}] declared", booking.status_code, booking.json().get("slot_name"), booking.json().get("status"))
    assert booking.status_code == 409, booking.text
    current['user'] = users[1]
    paid = client.post(f"/api/v2/me/orders/{order['id']}/simulate", json=dict(token=order['demo_token'], outcome='success'))
    assert paid.status_code == 200, paid.text
    assert paid.json()['status'] == 'fulfilled'
