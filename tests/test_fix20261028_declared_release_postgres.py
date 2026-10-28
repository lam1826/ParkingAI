"""Review 28/10/2026 R2-01 on real PostgreSQL: the manager's approval releases another account's
declaration of the plate while the declarer cancels that same row.

The approval holds the identity lock and releases with one bulk update as its last locking step,
taking no slot lock. The declarer's cancellation locks the slot, then waits on the row: the
approval commits, the cancellation finds the row already cancelled, and neither deadlocks.
Round 2: the deploy step (expansion.release_foreign_declarations, advisory identity locks in
plate order) and the release when another account is linked to the profile, on PostgreSQL.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, local
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from test_postgres_integration import _isolated_checkout_postgres, POSTGRES_TEST_URL
from core.clock import BUSINESS_TZ, business_now
from expansion import declared_bookings, portal_service
from expansion.portal_models import PortalAccountLink, PortalLinkRequest, PortalVehicleRequest
from expansion.simplified_customer_models import DeclaredParkingReservation
from expansion.simplified_customer_schemas import AdvanceBookingCreate
from expansion.site_models import ParkingSite
from models import Customer, ParkingSlot, Role, User, Vehicle, VehicleType, Zone

pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason="Requires isolated PostgreSQL service")


def test_approval_release_and_declarer_cancel_of_the_same_row_never_deadlock():
    with _isolated_checkout_postgres() as engine:
        now = business_now()
        start = (now + timedelta(hours=2)).replace(second=0, microsecond=0)
        with Session(engine) as db:
            roles = {name: Role(name=name) for name in ("customer", "manager")}
            site, kind = ParkingSite(name="Release race"), VehicleType(name="Release car")
            owner = Customer(full_name="Release owner", phone_number="RELEASE-OWNER")
            db.add_all([*roles.values(), site, kind, owner]); db.flush()
            owner_user = User(username="release-owner", role_id=roles["customer"].id, full_name="Owner", password_hash="unused")
            stranger = User(username="release-stranger", role_id=roles["customer"].id, full_name="Stranger", password_hash="unused")
            manager = User(username="release-manager", role_id=roles["manager"].id, full_name="Manager", password_hash="unused")
            zone = Zone(name="Release zone", site_id=site.id, capacity=2)
            db.add_all([owner_user, stranger, manager, zone]); db.flush()
            slots = [ParkingSlot(slot_name=f"REL-{i}", vehicle_type_id=kind.id, zone_id=zone.id) for i in range(2)]
            vehicle = Vehicle(license_plate="51A-246.80", vehicle_type_id=kind.id)
            db.add_all(slots + [vehicle, PortalAccountLink(user_id=owner_user.id, customer_id=owner.id, verification="test")])
            db.commit()
            # Declared while the plate was not verified to anyone.
            foreign = declared_bookings.create(db, stranger, AdvanceBookingCreate(site_id=site.id,
                license_plate=vehicle.license_plate, vehicle_type_id=kind.id, start_at=start.replace(tzinfo=BUSINESS_TZ),
                end_at=(start + timedelta(hours=2)).replace(tzinfo=BUSINESS_TZ), request_id=uuid4().hex))
            request = PortalVehicleRequest(customer_id=owner.id, license_plate=vehicle.license_plate, vehicle_type_id=kind.id)
            db.add(request)
            db.commit()
            ids = dict(manager=manager.id, stranger=stranger.id, row=foreign.id, request=request.id,
                vehicle=vehicle.id, owner=owner.id)

        released, worker = Event(), local()

        def hold_release(connection, cursor, statement, parameters, context, many):
            # The approval has updated the row (row lock held, not yet committed): let the
            # declarer lock the slot and block on that row before the approval commits.
            if getattr(worker, "approver", False) and statement.lstrip().upper().startswith("UPDATE DECLARED_PARKING_RESERVATIONS"):
                released.set()
                sleep(.5)

        def approve():
            worker.approver = True
            with Session(engine) as db:
                item = portal_service.resolve_vehicle(db, db.get(User, ids["manager"]), ids["request"], True)
                db.commit()
                return item.status

        def cancel():
            assert released.wait(10), "the approval never released the foreign row"
            with Session(engine) as db:
                row = declared_bookings.cancel(db, db.get(User, ids["stranger"]), ids["row"])
                db.commit()
                return row.status

        event.listen(engine, "after_cursor_execute", hold_release)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                approved, cancelled = pool.submit(approve), pool.submit(cancel)
                results = approved.result(timeout=30), cancelled.result(timeout=30)
        finally:
            event.remove(engine, "after_cursor_execute", hold_release)
        assert results == ("approved", "cancelled")
        with Session(engine) as db:
            assert db.get(DeclaredParkingReservation, ids["row"]).status == "cancelled"
            assert db.get(Vehicle, ids["vehicle"]).customer_id == ids["owner"]


def _verified_plate_with_rows(engine):
    """Owner profile with a linked account and a verified car; rows the earlier rule left on it."""
    start = (business_now() + timedelta(hours=3)).replace(second=0, microsecond=0)
    with Session(engine) as db:
        roles = {name: Role(name=name) for name in ("customer", "manager")}
        site, kind = ParkingSite(name="Deploy step"), VehicleType(name="Deploy car")
        owner = Customer(full_name="Deploy owner", phone_number="0901777666")
        db.add_all([*roles.values(), site, kind, owner]); db.flush()
        accounts = {name: User(username=f"deploy-{name}", role_id=roles["customer" if name != "manager" else "manager"].id,
            full_name=name, password_hash="unused") for name in ("owner", "stranger", "next", "manager")}
        zone = Zone(name="Deploy zone", site_id=site.id, capacity=4)
        db.add_all([*accounts.values(), zone]); db.flush()
        db.add_all([ParkingSlot(slot_name=f"DEP-{i}", vehicle_type_id=kind.id, zone_id=zone.id) for i in range(4)])
        cars = [Vehicle(license_plate=plate, vehicle_type_id=kind.id) for plate in ("51G-111.11", "51G-222.22")]
        db.add_all(cars + [PortalAccountLink(user_id=accounts["owner"].id, customer_id=owner.id, verification="test")])
        db.commit()
        body = lambda plate, hours: AdvanceBookingCreate(site_id=site.id, license_plate=plate, vehicle_type_id=kind.id,
            start_at=(start + timedelta(hours=hours)).replace(tzinfo=BUSINESS_TZ),
            end_at=(start + timedelta(hours=hours + 1)).replace(tzinfo=BUSINESS_TZ), request_id=uuid4().hex)
        # Declared while the plates were not verified to anyone; the earlier rule then kept them.
        rows = [declared_bookings.create(db, accounts["stranger"], body("51G-111.11", 0)).id,
                declared_bookings.create(db, accounts["stranger"], body("51G-222.22", 2)).id,
                declared_bookings.create(db, accounts["owner"], body("51G-222.22", 0)).id]
        db.commit()
        for car in cars:
            db.get(Vehicle, car.id).customer_id = owner.id
        db.commit()
        return dict(rows=rows, owner=owner.id, accounts={name: user.id for name, user in accounts.items()},
            phone=owner.phone_number)


def test_the_deploy_command_releases_foreign_rows_on_postgresql(capsys):
    from expansion import release_foreign_declarations as command
    with _isolated_checkout_postgres() as engine:
        ids = _verified_plate_with_rows(engine)
        url = engine.url.render_as_string(hide_password=False)
        assert command.main(["--database", url]) == 0
        assert json.loads(capsys.readouterr().out) == {"foreign_declarations": 2, "vehicles": 2, "applied": False}
        assert command.main(["--database", url, "--apply"]) == 0
        printed = capsys.readouterr().out
        assert json.loads(printed) == {"foreign_declarations": 2, "vehicles": 2, "released": 2, "skipped_vehicles": 0,
            "skipped_vehicle_ids": [], "applied": True}
        assert "parkingai" not in printed and "51G" not in printed
        with Session(engine) as db:
            assert [db.get(DeclaredParkingReservation, row).status for row in ids["rows"]] == ["cancelled", "cancelled", "confirmed"]


def test_linking_a_new_account_releases_the_earlier_account_rows_on_postgresql():
    with _isolated_checkout_postgres() as engine:
        ids = _verified_plate_with_rows(engine)
        with Session(engine) as db:
            # The admin unlinked the owner account; another account asks to be linked to the profile.
            db.execute(delete(PortalAccountLink).where(PortalAccountLink.user_id == ids["accounts"]["owner"]))
            request = PortalLinkRequest(user_id=ids["accounts"]["next"], phone_number=ids["phone"])
            db.add(request)
            db.commit()
            identity = request.id
        with Session(engine) as db:
            assert portal_service.resolve_link(db, db.get(User, ids["accounts"]["manager"]), identity, True).status == "approved"
        with Session(engine) as db:
            assert all(db.get(DeclaredParkingReservation, row).status == "cancelled" for row in ids["rows"])
            assert db.scalar(select(PortalAccountLink.user_id).where(PortalAccountLink.customer_id == ids["owner"])) == ids["accounts"]["next"]
