"""Integration round 2 (PORTAL), review 05/10/2026 #76 remainder (CL-LEDGER request 4).

/me/sessions rows carry the site of their slot, so the single-site customer screen
(supportLinkCandidates in supportState.js) leaves another site's stay out of the
support-link choices instead of filing a ticket into a queue nobody opens. A stay
without a slot reports site_id None, which makes the customer pick the receiving site.
"""
from datetime import timedelta

from core.clock import business_now
from expansion.portal_models import PortalSessionGrant
from expansion.site_models import ParkingSite
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.vehicle import Vehicle
from models.zone import Zone

from test_portal_api import onboard, portal  # noqa: F401


def _slot(db, site, vehicle_type, name):
    zone = Zone(name=f"Khu {name}", capacity=5, is_active=True, site_id=site.id)
    db.add(zone)
    db.flush()
    slot = ParkingSlot(zone_id=zone.id, vehicle_type_id=vehicle_type.id, slot_name=name, is_occupied=False, is_active=True)
    db.add(slot)
    db.flush()
    return slot


def _granted(db, customer_id, **values):
    session = ParkingSession(**values)
    db.add(session)
    db.flush()
    db.add(PortalSessionGrant(parking_session_id=session.id, customer_id=customer_id))
    db.flush()
    return session


def test_customer_sessions_carry_the_site_of_their_slot(portal, price_config):
    client, current, users, site, vehicle_type, db = portal
    body = onboard(portal)
    vehicle = db.get(Vehicle, body["vehicle_id"])
    other = ParkingSite(name="Bãi khác")
    db.add(other)
    db.flush()
    here, there = _slot(db, site, vehicle_type, "A-01"), _slot(db, other, vehicle_type, "B-01")
    now = business_now().replace(tzinfo=None)
    owner = vehicle.customer_id
    slotless = _granted(db, owner, vehicle_id=vehicle.id, check_in_time=now - timedelta(hours=9),
        status="cancelled", staff_in_id=users[0].id)
    elsewhere = _granted(db, owner, vehicle_id=vehicle.id, parking_slot_id=there.id, check_in_time=now - timedelta(hours=5),
        check_out_time=now - timedelta(hours=4), parking_fee=20000, status="completed",
        staff_in_id=users[0].id, staff_out_id=users[0].id)
    active = _granted(db, owner, vehicle_id=vehicle.id, parking_slot_id=here.id, check_in_time=now - timedelta(hours=1),
        status="active", staff_in_id=users[0].id)
    here.is_occupied = True
    db.commit()

    response = client.get("/api/v2/me/sessions")
    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["items"]}
    assert set(rows) == {active.id, elsewhere.id, slotless.id}
    assert rows[active.id]["site_id"] == site.id and rows[active.id]["slot_name"] == "A-01"
    assert rows[elsewhere.id]["site_id"] == other.id and rows[elsewhere.id]["zone_name"] == "Khu B-01"
    assert rows[slotless.id]["site_id"] is None and rows[slotless.id]["slot_name"] is None

    # The vehicle list keeps one shape: the current stay's site, or None without a stay.
    vehicles = client.get("/api/v2/me/vehicles").json()["items"]
    assert [(row["id"], row["current_session_id"], row["site_id"]) for row in vehicles] == [(vehicle.id, active.id, site.id)]
    db.delete(db.get(PortalSessionGrant, active.id))
    db.commit()
    idle = client.get("/api/v2/me/vehicles").json()["items"]
    assert idle[0]["current_session_id"] is None and idle[0]["site_id"] is None
