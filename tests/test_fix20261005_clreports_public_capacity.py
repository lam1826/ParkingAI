"""#59: public capacity and the customer AI context must not count slots of deactivated vehicle types.

availability(), served_vehicle_types() and admission already exclude inactive vehicle types; the
public 'N vị trí đang hoạt động' count must use the same rule.
"""
from test_core_crud_permissions import core_access  # noqa: F401 -- shared isolated core fixture
from models.parking_slot import ParkingSlot
from models.vehicle_type import VehicleType
from expansion.customer_assistant import customer_context
from expansion.public_profile import capacity_summary


def test_deactivated_vehicle_type_slots_are_not_public_active_capacity(client, db_session, core_access):
    site, zone, car = core_access["site"], core_access["zones"], core_access["vehicle-types"]
    truck = VehicleType(name="Xe tải công khai", description="truck")
    db_session.add(truck)
    db_session.flush()
    db_session.add_all([
        ParkingSlot(zone_id=zone.id, vehicle_type_id=car.id, slot_name="A-02", is_active=True, is_occupied=False),
        ParkingSlot(zone_id=zone.id, vehicle_type_id=truck.id, slot_name="T-01", is_active=True, is_occupied=False)])
    db_session.commit()
    before = capacity_summary(db_session, site.id)["slots"]

    deactivated = client.put(f"/api/v1/vehicle-types/{truck.id}", headers=core_access["headers"]["manager"],
        json={"is_active": False})
    assert deactivated.status_code == 200, deactivated.text

    public = client.get(f"/api/v2/public/sites/{site.id}")
    assert public.status_code == 200, public.text
    data = public.json()
    availability = client.get(f"/api/v2/sites/{site.id}/availability", headers=core_access["headers"]["staff"]).json()
    assert data["capacity"]["slots"] == before - 1
    assert data["capacity"]["slots"] == availability["total"]
    assert data["capacity"]["slots"] == sum(row["slot_count"] for row in data["vehicle_types"])

    context = customer_context(db_session, site.id)
    assert context["published"]["capacity"]["slots"] == context["current_availability"]["total"]
