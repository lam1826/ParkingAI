"""#12 fix: does a booking several days ahead block today's unrelated admission?"""
from datetime import timedelta
import pytest
from core.clock import BUSINESS_TZ
from models.parking_slot import ParkingSlot
from expansion import declared_bookings
from test_expansion_sites import env  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401


@pytest.mark.parametrize("days", [0,2])
def test_walk_in_today_is_independent_of_future_booking(customer_env, days):
    e = customer_env
    e.slot.zone.capacity += 1
    e.db.add(ParkingSlot(zone_id=e.slot.zone_id, vehicle_type_id=e.slot.vehicle_type_id, slot_name="ALT"))
    e.db.commit()
    start = e.now + (timedelta(days=days) if days else timedelta(minutes=10))
    booked = post_booking(e, start_at=start.replace(tzinfo=BUSINESS_TZ).isoformat(),
                          end_at=(start + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ).isoformat())
    assert booked.status_code == 201, booked.text
    e.actor["user"] = e.staff
    response = e.client.post(f"/api/v2/sites/{e.a.id}/check-in",
                             json={"license_plate": "51A-887.76", "vehicle_type_id": e.slot.vehicle_type_id})
    assert response.status_code == 201, response.text


def test_reserved_arrival_with_unrelated_booking_three_days_ahead(customer_env):
    from test_expansion_sites import reserve
    e = customer_env
    row = reserve(e)  # staff reservation for e.vehicle, now..now+2h, on e.slot
    start = e.now + timedelta(days=3)
    e.actor["user"] = e.stranger
    booked = post_booking(e, license_plate=e.vehicle.license_plate, vehicle_type_id=e.vehicle.vehicle_type_id,
                          start_at=start.replace(tzinfo=BUSINESS_TZ).isoformat(),
                          end_at=(start + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ).isoformat())
    assert booked.status_code == 201, booked.text
    e.actor["user"] = e.staff
    response = e.client.post(f"/api/v2/sites/{e.a.id}/reservations/{row.id}/arrive")
    assert response.status_code in (200, 201), response.text
