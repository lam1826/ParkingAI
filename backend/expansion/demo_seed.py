"""Create a NEW isolated SQLite student demo with explicitly synthetic history.

Never upgrades or writes an existing database. Publication uses an exclusive
hard link so a file appearing after the initial check cannot be overwritten.
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def _seed_rows(db, password, now):
    from sqlalchemy import select
    from expansion.portal_models import PortalAccountLink, PortalVehicleOwnership, PortalSessionGrant, SubscriptionPlan
    from expansion.site_models import ParkingSite, SiteMembership
    from expansion.vision_models import Camera
    from models.customer import Customer
    from models.parking_session import ParkingSession
    from models.parking_slot import ParkingSlot
    from models.price_config import PriceConfig
    from models.role import Role
    from models.user import User
    from models.vehicle import Vehicle
    from models.vehicle_type import VehicleType
    from models.zone import Zone
    from services.auth_service import AuthService

    roles = {name: Role(name=name, description="Tài khoản dùng thử đồ án") for name in ("admin", "manager", "staff", "customer")}
    db.add_all(roles.values()); db.flush()
    users = {}
    for name, role in roles.items():
        users[name] = User(username=f"{name}_demo", role_id=role.id,
            password_hash=AuthService.get_password_hash(password), full_name=f"DEMO {name}", is_active=True)
    db.add_all(users.values()); db.flush()

    site_a = db.scalar(select(ParkingSite).order_by(ParkingSite.id))
    if site_a is None:
        site_a = ParkingSite(name="DEMO - Bãi A", address="Dữ liệu giả lập phục vụ đồ án", is_active=True)
        db.add(site_a)
    else:
        site_a.name = "DEMO - Bãi A"
        site_a.address = "Dữ liệu giả lập phục vụ đồ án"
    site_b = ParkingSite(name="DEMO - Bãi B", address="Dữ liệu giả lập phục vụ đồ án", is_active=True)
    db.add(site_b); db.flush()
    for role in ("staff", "manager"):
        db.add(SiteMembership(site_id=site_a.id, user_id=users[role].id, role=role))
    types = [VehicleType(name="Ô tô DEMO", description="Loại xe dùng thử"),
             VehicleType(name="Xe máy DEMO", description="Loại xe dùng thử")]
    db.add_all(types); db.flush()
    for vehicle_type, amount in zip(types, (20000, 5000)):
        db.add(PriceConfig(vehicle_type_id=vehicle_type.id, ticket_type="HOURLY", price=amount,
            effective_date=(now - timedelta(days=90)).date(), is_active=True))

    slots = {}
    for site, prefix in ((site_a, "A"), (site_b, "B")):
        zone = Zone(site_id=site.id, name=f"DEMO {prefix} - Khu chính", capacity=16, is_active=True)
        db.add(zone); db.flush()
        slots[site.id] = [ParkingSlot(zone_id=zone.id, vehicle_type_id=types[index // 8].id,
            slot_name=f"DEMO-{prefix}-{index + 1:02}", is_active=True, is_occupied=False) for index in range(16)]
        db.add_all(slots[site.id]); db.flush()
        db.add_all([Camera(site_id=site.id, zone_id=zone.id, name=f"Điện thoại {prefix} - Cổng vào", direction="entry", retention_hours=24),
                    Camera(site_id=site.id, zone_id=zone.id, name=f"Điện thoại {prefix} - Cổng ra", direction="exit", retention_hours=24)])
        for vehicle_type, amount in zip(types, (1200000, 180000)):
            db.add(SubscriptionPlan(name=f"DEMO {prefix} - {vehicle_type.name} 30 ngày", site_id=site.id,
                vehicle_type_id=vehicle_type.id, duration_days=30, price=amount, is_active=True))

    customer = Customer(full_name="Khách hàng DEMO", phone_number="0900000001", email="customer@example.com")
    db.add(customer); db.flush()
    db.add(PortalAccountLink(user_id=users["customer"].id, customer_id=customer.id,
        verified_by_id=users["admin"].id, verification="demo_seed", created_at=now - timedelta(days=57)))
    own_vehicles = [Vehicle(license_plate="30A-123.45", vehicle_type_id=types[0].id, customer_id=customer.id),
                    Vehicle(license_plate="59A1-123.45", vehicle_type_id=types[1].id, customer_id=customer.id)]
    db.add_all(own_vehicles); db.flush()
    for vehicle in own_vehicles:
        db.add(PortalVehicleOwnership(customer_id=customer.id, vehicle_id=vehicle.id,
            approved_by_id=users["admin"].id, approved_at=now - timedelta(days=57)))

    # Completed synthetic sessions never create cash receipts or real revenue.
    # Each demo car has its own slot; visits finish before the next hour.
    history_count = 0
    pattern = {7: 3, 8: 7, 9: 4, 12: 2, 17: 8, 18: 6, 20: 2}
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=56)
    for site, prefix in ((site_a, "A"), (site_b, "B")):
        history_vehicles = [Vehicle(license_plate=f"DEMO-{prefix}{index + 1:03}", vehicle_type_id=types[0].id) for index in range(8)]
        db.add_all(history_vehicles); db.flush()
        for day_offset in range(56):
            day = start_day + timedelta(days=day_offset)
            for hour, count in pattern.items():
                if day.weekday() >= 5:
                    count = max(1, count // 2)
                if prefix == "B":
                    count = max(1, count // 2)
                for index in range(count):
                    entered = day + timedelta(hours=hour, minutes=5 + index)
                    identity = str(uuid5(NAMESPACE_URL, f"parkingai-synthetic:{prefix}:{entered.isoformat()}:{index}"))
                    db.add(ParkingSession(id=identity, vehicle_id=history_vehicles[index].id,
                        parking_slot_id=slots[site.id][index].id, check_in_time=entered,
                        check_out_time=entered + timedelta(minutes=30), parking_fee=0, status="completed",
                        staff_in_id=users["admin"].id, staff_out_id=users["admin"].id,
                        image_in_url="demo://synthetic-history", created_at=entered, updated_at=entered + timedelta(minutes=30)))
                    history_count += 1
    # One owned live bike demonstrates the customer's current parking location.
    active = ParkingSession(vehicle_id=own_vehicles[1].id, parking_slot_id=slots[site_a.id][8].id,
        check_in_time=now - timedelta(minutes=20), status="active", staff_in_id=users["staff"].id,
        image_in_url="demo://seed-active")
    slots[site_a.id][8].is_occupied = True
    db.add(active); db.flush()
    db.add(PortalSessionGrant(parking_session_id=active.id, customer_id=customer.id))
    db.commit()
    return {"parkingai_demo": True, "synthetic_history": True, "history_days": 56,
        "synthetic_closed_sessions": history_count, "active_sessions": 1, "real_revenue_seeded": 0,
        "sites": [{"id": site.id, "name": site.name} for site in (site_a, site_b)],
        "usernames": [user.username for user in users.values()],
        "customer_vehicle_plates": [vehicle.license_plate for vehicle in own_vehicles],
        "note": "Dữ liệu tạo tự động phục vụ đồ án; không phải số liệu một bãi xe thật."}


def create_demo(database_path, password):
    target = Path(database_path).expanduser().resolve()
    marker = Path(str(target) + ".demo.json")
    if target.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Use a new .db/.sqlite/.sqlite3 file for the isolated demo")
    if target.exists() or marker.exists():
        raise FileExistsError("Demo target or marker already exists; neither was changed")
    if len(password) < 10 or len(password.encode("utf-8")) > 72:
        raise ValueError("Demo password must contain at least 10 characters and at most 72 UTF-8 bytes")
    target.parent.mkdir(parents=True, exist_ok=True)
    from core.clock import business_now
    from database import create_database_engine
    from db_rollout import initialize_database, check_database_readiness
    from sqlalchemy.orm import Session

    # The scratch directory is created inside the resolved target parent and
    # contains only files made by this invocation. It is removed on any error.
    with tempfile.TemporaryDirectory(prefix=".parkingai-demo-", dir=target.parent) as directory:
        candidate = Path(directory).resolve() / "candidate.db"
        if candidate.parent.parent != target.parent:
            raise RuntimeError("Demo scratch path is outside the requested directory")
        initialize_database(candidate)
        engine = create_database_engine("sqlite:///" + candidate.as_posix())
        try:
            with Session(engine) as db:
                details = _seed_rows(db, password, business_now())
            check_database_readiness(engine)
        finally:
            engine.dispose()
        details.update(generated_at=business_now().isoformat(),
            database=str(target), initial_database_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
        candidate_marker = candidate.with_suffix(".json")
        candidate_marker.write_text(json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # os.link fails if the destination exists: no check-then-replace race.
        os.link(candidate_marker, marker)
        try:
            os.link(candidate, target)
        except Exception:
            marker.unlink()
            raise
    return details


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--password", default="DemoParkingAI!2026", help="Password for local DEMO accounts only")
    args = parser.parse_args()
    # Any ambient production URL is irrelevant to this CLI. All real work is
    # against the explicit scratch engine; global imports stay in memory.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    try:
        print(json.dumps(create_demo(args.database, args.password), ensure_ascii=False, indent=2))
    except (ValueError, FileExistsError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
