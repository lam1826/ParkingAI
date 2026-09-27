"""Approval and admission must share one PostgreSQL lock order."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.clock import business_now
from core import vehicle_identity
from expansion import portal_service
from expansion.portal_models import PortalVehicleOwnership, PortalVehicleRequest
from expansion.site_models import ParkingSite
from models import Customer, ParkingSession, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone
from services.parking_service import ParkingService
from test_postgres_integration import POSTGRES_TEST_URL, _isolated_checkout_postgres

pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Requires isolated PostgreSQL service")


def test_same_manager_can_approve_while_admitting_a_new_vehicle(monkeypatch):
    """A pending approval must not hold the cashier row while waiting for entry.

    Pause actual admission after its identity lock, then start actual approval
    using a punctuation variant. Resume entry only when approval reaches that
    same lock. The former operator-first approval deadlocks at the session FK.
    """
    with _isolated_checkout_postgres() as engine:
        with Session(engine) as db:
            role = Role(name="manager")
            customer = Customer(full_name="Concurrent owner", phone_number="PG-APPROVAL-OWNER")
            kind, site = VehicleType(name="Approval car"), ParkingSite(name="Approval site")
            db.add_all([role, customer, kind, site])
            db.flush()
            manager = User(username="approval-manager", password_hash="unused", full_name="Manager", role_id=role.id)
            zone = Zone(name="Approval zone", site_id=site.id, capacity=1)
            request = PortalVehicleRequest(customer_id=customer.id, license_plate="30A-123.45", vehicle_type_id=kind.id)
            db.add_all([manager, zone, request])
            db.flush()
            slot = ParkingSlot(slot_name="APPROVAL-1", vehicle_type_id=kind.id, zone_id=zone.id)
            db.add_all([slot, PriceConfig(vehicle_type_id=kind.id, ticket_type="HOURLY", price=10000,
                                        effective_date=business_now().date())])
            db.commit()
            manager_id, request_id = manager.id, request.id
            kind_id, slot_id, customer_id = kind.id, slot.id, customer.id

        entry_locked, approval_waiting = Event(), Event()
        original_lock = vehicle_identity.lock_identity

        def scheduled_lock(db, type_id, plate):
            if db.info.get("operation") == "approval":
                approval_waiting.set()
            original_lock(db, type_id, plate)
            if db.info.get("operation") == "entry":
                entry_locked.set()
                assert approval_waiting.wait(10), "Approval did not reach the identity lock"

        monkeypatch.setattr(vehicle_identity, "lock_identity", scheduled_lock)
        monkeypatch.setattr(portal_service, "lock_identity", scheduled_lock)

        def admit():
            with Session(engine, info={"operation": "entry"}) as db:
                return ParkingService(db).check_in("30A12345", kind_id, manager_id, parking_slot_id=slot_id)

        def approve():
            assert entry_locked.wait(10), "Admission did not acquire the identity lock"
            with Session(engine, info={"operation": "approval"}) as db:
                return portal_service.resolve_vehicle(db, db.get(User, manager_id), request_id, True).status

        with ThreadPoolExecutor(max_workers=2) as pool:
            entered, approved = pool.submit(admit), pool.submit(approve)
            # Consume both results even when one fails, allowing its rollback to
            # release the other worker and retaining the original DB failure.
            outcomes, errors = [], []
            for future in (entered, approved):
                try:
                    outcomes.append(future.result(timeout=20))
                except Exception as exc:
                    errors.append(exc)
            assert not errors, [repr(error) for error in errors]
        assert outcomes[1] == "approved"
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(Vehicle)) == 1
            vehicle = db.scalar(select(Vehicle))
            assert vehicle.customer_id == customer_id
            assert db.scalar(select(func.count()).select_from(ParkingSession)) == 1
            assert db.get(ParkingSession, outcomes[0]["session_id"]).vehicle_id == vehicle.id
            assert db.get(ParkingSlot, slot_id).is_occupied
            assert db.scalar(select(func.count()).select_from(PortalVehicleOwnership)) == 1
            assert db.get(PortalVehicleRequest, request_id).reviewed_by_id == manager_id
