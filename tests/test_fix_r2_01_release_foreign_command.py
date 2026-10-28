"""Review 28/10/2026 R2-01, deploy step (DESIGN_R2-01 section 4).

A declaration another account made before the fix, on a plate that was already
verified to a customer profile, is never consumed by or shown the owner's car,
but while it lives it still blocks the owner's own bookings of the plate
(plate exclusivity). ``expansion.release_foreign_declarations`` is the one-off
maintenance command run before rollout: a read-only count by default, and with
``--apply`` the same ``release_foreign`` the approval runs, under
``lock_identity``, in one transaction. It prints counts only.
"""
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.clock import business_now
from core.vehicle_identity import canonical_identity
from database import Base
from expansion import release_foreign_declarations as command
from expansion.portal_models import PortalAccountLink
from expansion.simplified_customer_models import DeclaredParkingReservation as Booking
from expansion.site_models import ParkingSite
from models import Customer, ParkingSlot, Role, User, Vehicle, VehicleType, Zone
from test_fix_r2_01_declared_owner_privacy import _alternate_slot, _at
from test_expansion_sites import env  # noqa: F401
from test_simplified_customer_flows import customer_env, post_booking  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _row_from_before_the_fix(db, *, site_id, slot_id, user_id, plate, type_id, start, request_id):
    """The state the earlier rule left: another account's live declaration of a verified plate."""
    row = Booking(site_id=site_id, slot_id=slot_id, user_id=user_id, license_plate=plate,
        normalized_plate=canonical_identity(plate), vehicle_type_id=type_id, start_at=start,
        end_at=start + timedelta(hours=2), arrival_deadline=start + timedelta(minutes=15), request_id=request_id)
    db.add(row)
    db.commit()
    return row


def test_the_deploy_step_counts_then_releases_only_rows_left_from_before_the_fix(customer_env):
    e = customer_env
    _alternate_slot(e)
    foreign = _row_from_before_the_fix(e.db, site_id=e.a.id, slot_id=e.slot.id, user_id=e.stranger.id,
        plate=e.vehicle.license_plate, type_id=e.vehicle.vehicle_type_id, start=e.now + timedelta(minutes=10),
        request_id="declared-before-the-fix-02")
    unregistered = post_booking(e, request_id="unregistered-plate-0002")
    assert unregistered.status_code == 201, unregistered.text
    e.actor["user"] = e.account
    own = post_booking(e, license_plate=e.other.license_plate, start_at=_at(e, 180), end_at=_at(e, 240),
        request_id="owner-other-vehicle-01")
    assert own.status_code == 201, own.text
    # Before the step the owner is still refused on the plate (plate exclusivity).
    body = dict(license_plate=e.vehicle.license_plate, vehicle_type_id=e.vehicle.vehicle_type_id,
        start_at=_at(e, 30), end_at=_at(e, 60), request_id="owner-after-the-step-01")
    assert post_booking(e, **body).status_code == 409
    counted = command.foreign_counts(e.db)
    assert counted == {"foreign_declarations": 1, "vehicles": 1}
    e.db.expire_all()
    assert e.db.get(Booking, foreign.id).status == "confirmed", "the count changes nothing"
    result = command.release_foreign_declarations(e.db)
    e.db.commit()
    assert result == {"foreign_declarations": 1, "vehicles": 1, "released": 1, "skipped_vehicles": 0,
        "skipped_vehicle_ids": []}
    e.db.expire_all()
    assert e.db.get(Booking, foreign.id).status == "cancelled"
    # The owner's own rows and a plate nobody owns are untouched.
    assert e.db.get(Booking, own.json()["id"]).status == "confirmed"
    assert e.db.get(Booking, unregistered.json()["id"]).status == "confirmed"
    owner = post_booking(e, **body)
    assert owner.status_code == 201, owner.text
    assert command.foreign_counts(e.db) == {"foreign_declarations": 0, "vehicles": 0}


def _file_database(path):
    """A small file database with one owner, one stranger and the stranger's row from before the fix."""
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    start = (business_now() + timedelta(days=1)).replace(second=0, microsecond=0)
    with Session(engine) as db:
        role, kind, site = Role(name="customer"), VehicleType(name="Ô tô bảo trì"), ParkingSite(name="Bãi bảo trì")
        owner = Customer(full_name="Chủ xe", phone_number="0901999888")
        db.add_all([role, kind, site, owner])
        db.flush()
        account = User(username="maintenance-owner", role_id=role.id, full_name="Chủ xe", password_hash="unused")
        stranger = User(username="maintenance-stranger", role_id=role.id, full_name="Khách khác", password_hash="unused")
        zone = Zone(name="Khu bảo trì", site_id=site.id, capacity=1)
        db.add_all([account, stranger, zone])
        db.flush()
        slot = ParkingSlot(slot_name="BT-01", zone_id=zone.id, vehicle_type_id=kind.id)
        vehicle = Vehicle(license_plate="51F-777.88", vehicle_type_id=kind.id, customer_id=owner.id)
        db.add_all([slot, vehicle, PortalAccountLink(user_id=account.id, customer_id=owner.id, verification="test")])
        db.flush()
        row = _row_from_before_the_fix(db, site_id=site.id, slot_id=slot.id, user_id=stranger.id,
            plate=vehicle.license_plate, type_id=kind.id, start=start, request_id="maintenance-before-fix")
        identity = row.id
    engine.dispose()
    return identity


def test_a_plate_shared_by_legacy_vehicles_is_counted_once_and_reported_for_staff(tmp_path):
    """One foreign row on an identity two legacy vehicles share: counted once, skipped by id, never released blind."""
    path = tmp_path / "shared.db"
    identity = _file_database(path)
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with Session(engine) as db:
        first = db.scalar(select(Vehicle).where(Vehicle.license_plate == "51F-777.88"))
        other = Customer(full_name="Chủ xe cũ", phone_number="0901999777")
        db.add(other)
        db.flush()
        # Legacy data: the same identity spelled differently, owned by another profile.
        twin = Vehicle(license_plate="51F77788", vehicle_type_id=first.vehicle_type_id, customer_id=other.id)
        db.add(twin)
        db.commit()
        ids = sorted([first.id, twin.id])
        assert command.foreign_counts(db) == {"foreign_declarations": 1, "vehicles": 2}
        result = command.release_foreign_declarations(db)
        db.commit()
        assert result == {"foreign_declarations": 1, "vehicles": 2, "released": 0, "skipped_vehicles": 2,
            "skipped_vehicle_ids": ids}
        assert db.scalar(select(Booking.status).where(Booking.id == identity)) == "confirmed"
    engine.dispose()


def _run(*arguments):
    environment = {key: value for key, value in os.environ.items() if key not in {"DATABASE_URL", "SECRET_KEY"}}
    return subprocess.run([sys.executable, "-m", "expansion.release_foreign_declarations", *arguments], cwd=BACKEND,
        env={**environment, "PYTHONIOENCODING": "utf-8"}, capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_the_command_is_a_dry_run_unless_apply_is_given(tmp_path):
    path = tmp_path / "maintenance.db"
    identity = _file_database(path)
    dry = _run("--database", str(path))
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout) == {"foreign_declarations": 1, "vehicles": 1, "applied": False}
    assert "51F" not in dry.stdout + dry.stderr and "maintenance-" not in dry.stdout + dry.stderr
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with Session(engine) as db:
        assert db.scalar(select(Booking.status).where(Booking.id == identity)) == "confirmed"
    applied = _run("--database", str(path), "--apply")
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout) == {"foreign_declarations": 1, "vehicles": 1, "released": 1,
        "skipped_vehicles": 0, "skipped_vehicle_ids": [], "applied": True}
    with Session(engine) as db:
        assert db.scalar(select(Booking.status).where(Booking.id == identity)) == "cancelled"
    engine.dispose()
    again = _run("--database", f"sqlite:///{path.as_posix()}")
    assert json.loads(again.stdout) == {"foreign_declarations": 0, "vehicles": 0, "applied": False}
    # A mistyped path never creates an empty database.
    missing = _run("--database", str(tmp_path / "missing.db"))
    assert missing.returncode == 2 and not (tmp_path / "missing.db").exists()
