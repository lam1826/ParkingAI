"""Namespaced, additive online showcase data for SQLite and PostgreSQL.

Dry-run is read-only. Apply never resets a database, changes existing accounts,
or creates a payment. Supply independently generated password hashes via file.
"""
import argparse
import json
import re
from datetime import timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from core.clock import business_now
from expansion.portal_models import PortalAccountLink, PortalVehicleOwnership, PortalSessionGrant, SubscriptionPlan
from expansion.site_models import ParkingSite, SiteMembership
from expansion.vision_models import Camera
from models import Customer, ParkingSession, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone

ACCOUNTS = {"admin": "admin", "manager_a": "manager", "manager_b": "manager", "staff_a": "staff", "staff_b": "staff", "customer_a": "customer", "customer_b": "customer"}


def preview(db, namespace):
    if not re.fullmatch(r"demo[a-z0-9]{4,8}", namespace):
        raise ValueError("Namespace must be demo followed by 4–8 lowercase letters/digits")
    names = [f"{namespace}_{name}" for name in ACCOUNTS]
    existing = db.scalar(select(func.count()).select_from(User).where(User.username.in_(names)))
    if existing not in {0, 7}:
        raise ValueError("Partial namespace already exists; inspect its manifest before applying")
    return {"namespace": namespace, "existing_accounts": existing, "usernames": names,
            "sites": [f"DEMO {namespace} - Bãi {letter}" for letter in "AB"],
            "planned": {"accounts": 7, "sites": 2, "slots": 32, "plans": 4, "cameras": 4, "history_days": 56},
            "synthetic_history": True, "real_revenue_seeded": 0}


def seed(db, namespace, password_hashes):
    description = preview(db, namespace)
    if set(password_hashes) != set(ACCOUNTS) or any(not re.fullmatch(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}", value) for value in password_hashes.values()):
        raise ValueError("Exactly seven generated bcrypt hashes are required")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": "showcase:" + namespace})
        description = preview(db, namespace)
    marker = "DEMO " + namespace
    now = business_now().replace(microsecond=0)
    manifest = {**description, "ids": {}, "created": {}, "generated_at": now.isoformat()}

    def ensure(model, key, lookup, values, *, shared=False):
        row = db.scalar(select(model).filter_by(**lookup))
        if row is None:
            row = model(**lookup, **values)
            db.add(row); db.flush()
            manifest["created"][model.__tablename__] = manifest["created"].get(model.__tablename__, 0) + 1
        elif not description["existing_accounts"] and not shared:
            raise ValueError("Namespace collision; existing data was not changed")
        manifest["ids"][key] = row.id
        return row

    roles = {name: ensure(Role, "role_" + name, {"name": name}, {"description": "Vai trò hệ thống"}, shared=True) for name in set(ACCOUNTS.values())}
    users = {}
    for account, role in ACCOUNTS.items():
        user = ensure(User, account, {"username": f"{namespace}_{account}"},
            {"role_id": roles[role].id, "password_hash": password_hashes[account], "full_name": f"{marker} {account}", "is_active": True})
        if user.password_hash != password_hashes[account] or user.role_id != roles[role].id or user.full_name != f"{marker} {account}":
            raise ValueError("Existing demo account differs; passwords and roles were not overwritten")
        users[account] = user

    kinds = []
    for name, price in (("Ô tô", 20000), ("Xe máy", 5000)):
        kind = ensure(VehicleType, "type_" + name, {"name": f"{marker} {name}"}, {"description": "Loại xe chỉ dùng trình diễn đồ án"})
        ensure(PriceConfig, "price_" + name, {"vehicle_type_id": kind.id, "is_active": True},
            {"ticket_type": "HOURLY", "price": price, "effective_date": (now - timedelta(days=90)).date()})
        kinds.append(kind)

    for letter in "AB":
        suffix = letter.lower()
        site = ensure(ParkingSite, "site_" + suffix, {"name": f"{marker} - Bãi {letter}"},
            {"address": "Dữ liệu tổng hợp phục vụ đồ án; không phải số liệu vận hành thật", "is_active": True, "created_at": now})
        anchor = site.created_at.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
        for role in ("manager", "staff"):
            ensure(SiteMembership, role + "_membership_" + suffix, {"site_id": site.id, "user_id": users[role + "_" + suffix].id}, {"role": role})
        zone = ensure(Zone, "zone_" + suffix, {"name": f"{marker} {letter} - Khu chính"}, {"site_id": site.id, "capacity": 16, "is_active": True})
        if zone.site_id != site.id:
            raise ValueError("Zone scope changed; inspect the manifest")
        slots = [ensure(ParkingSlot, f"slot_{suffix}_{i}", {"slot_name": f"{namespace.upper()}-{letter}-{i+1:02}"},
            {"zone_id": zone.id, "vehicle_type_id": kinds[i // 8].id, "is_active": True, "is_occupied": False}) for i in range(16)]
        for direction in ("entry", "exit"):
            ensure(Camera, f"camera_{suffix}_{direction}", {"site_id": site.id, "name": f"Điện thoại DEMO {letter} {direction}"},
                {"zone_id": zone.id, "direction": direction, "retention_hours": 24, "is_active": True})
        for kind, price in zip(kinds, (1200000, 180000)):
            ensure(SubscriptionPlan, f"plan_{suffix}_{kind.id}", {"name": f"{marker} {letter} - {kind.name} 30 ngày", "site_id": site.id},
                {"vehicle_type_id": kind.id, "duration_days": 30, "price": price, "is_active": True})
        owner = ensure(Customer, "customer_profile_" + suffix, {"phone_number": f"{namespace.upper()}-{letter}"},
            {"full_name": f"Khách {marker} {letter}", "email": f"{namespace}-{suffix}@example.invalid"})
        ensure(PortalAccountLink, "customer_link_" + suffix, {"user_id": users["customer_" + suffix].id},
            {"customer_id": owner.id, "verified_by_id": users["admin"].id, "verification": "showcase_seed"})
        own = []
        for i, kind in enumerate(kinds):
            car = ensure(Vehicle, f"owned_{suffix}_{i}", {"license_plate": f"{namespace.upper()}-{letter}{i}"}, {"vehicle_type_id": kind.id, "customer_id": owner.id})
            ensure(PortalVehicleOwnership, f"ownership_{suffix}_{i}", {"customer_id": owner.id, "vehicle_id": car.id},
                {"approved_by_id": users["admin"].id, "approved_at": anchor - timedelta(days=57)})
            own.append(car)
        history_cars = [ensure(Vehicle, f"history_car_{suffix}_{i}", {"license_plate": f"{namespace.upper()}-{letter}H{i}"}, {"vehicle_type_id": kinds[0].id}) for i in range(8)]
        history_ids = []
        for day_offset in range(56):
            day = anchor - timedelta(days=56-day_offset)
            for hour, volume in ((7, 3), (8, 7), (9, 4), (12, 2), (17, 8), (18, 6), (20, 2)):
                count = max(1, volume // (2 if day.weekday() >= 5 else 1) // (2 if letter == "B" else 1))
                for i in range(count):
                    entered = day + timedelta(hours=hour, minutes=5+i)
                    identity = str(uuid5(NAMESPACE_URL, f"parkingai:{namespace}:{letter}:{entered.isoformat()}:{i}"))
                    row = db.get(ParkingSession, identity)
                    if row is None:
                        db.add(ParkingSession(id=identity, vehicle_id=history_cars[i].id, parking_slot_id=slots[i].id,
                            check_in_time=entered, check_out_time=entered+timedelta(minutes=30), parking_fee=0, status="completed",
                            staff_in_id=users["staff_"+suffix].id, staff_out_id=users["staff_"+suffix].id,
                            image_in_url="demo://synthetic-history/"+namespace, created_at=entered, updated_at=entered+timedelta(minutes=30)))
                        manifest["created"]["parking_sessions"] = manifest["created"].get("parking_sessions", 0) + 1
                    history_ids.append(identity)
        db.flush()
        manifest["ids"]["history_" + suffix] = history_ids
        identity = str(uuid5(NAMESPACE_URL, f"parkingai:{namespace}:{letter}:initial-session"))
        if not db.get(ParkingSession, identity):
            if slots[8].is_occupied or db.scalar(select(ParkingSession.id).where(ParkingSession.vehicle_id == own[1].id, ParkingSession.status == "active")):
                raise ValueError("Demo vehicle or slot already occupied; no records were overwritten")
            slots[8].is_occupied = True
            db.add(ParkingSession(id=identity, vehicle_id=own[1].id, parking_slot_id=slots[8].id,
                check_in_time=now-timedelta(minutes=10), status="active", staff_in_id=users["staff_"+suffix].id, image_in_url="demo://seed-active/"+namespace))
            db.flush()
            db.add(PortalSessionGrant(parking_session_id=identity, customer_id=owner.id))
        manifest["ids"]["initial_session_"+suffix] = identity
    db.flush()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--hashes', type=Path)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    from database import engine
    with Session(engine) as db:
        if not args.apply:
            print(json.dumps(preview(db, args.namespace), ensure_ascii=False))
            return
        if not args.hashes or not args.manifest:
            parser.error('--apply requires --hashes and --manifest outside Git')
        hashes = json.loads(args.hashes.read_text(encoding='utf-8'))
        result = seed(db, args.namespace, hashes)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        # Preserve recovery evidence even if process/network fails after commit.
        pending = args.manifest.with_suffix('.pending.json')
        pending.write_text(json.dumps({**result, 'commit_status': 'prepared'}, ensure_ascii=False, indent=2), encoding='utf-8')
        db.commit()
        args.manifest.write_text(json.dumps({**result, 'commit_status': 'committed'}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'namespace': args.namespace, 'committed': True, 'created': result['created'], 'manifest': str(args.manifest)}))


if __name__ == '__main__':
    main()
