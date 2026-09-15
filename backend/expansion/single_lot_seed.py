"""Build a NEW one-lot academic database and private random demo credentials.

The cash ledger is synthetic fixture data in this isolated database. This
module never contacts a payment provider or receives money.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

PROFILE = "single-lot-academic-v1"
ROLES = ("admin", "manager", "staff", "customer")


def _seed_rows(db, credentials, now):
    from sqlalchemy import select
    from expansion.portal_models import PortalAccountLink, PortalVehicleOwnership, PortalSessionGrant, SubscriptionPlan
    from expansion.site_models import ParkingSite, SiteMembership
    from expansion.vision_models import Camera
    from models import Customer, MonthlyPass, ParkingCard, ParkingSession, ParkingSlot, PriceConfig, Role, User, Vehicle, VehicleType, Zone
    from models.cash_shift import CashShift
    from services.auth_service import AuthService
    from services.parking_service import ParkingService
    from services.payment_service import PaymentService
    from crud.parking_session import resolve_check_in_billing_snapshot

    now = now.replace(microsecond=0)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    roles = {name: Role(name=name, description="Vai trò DEMO đồ án") for name in ROLES}
    db.add_all(roles.values())
    db.flush()
    users = {name: User(username=f"{name}_demo", role_id=roles[name].id, full_name=f"DEMO {name}",
                       password_hash=AuthService.get_password_hash(credentials[f"{name}_demo"]), is_active=True)
             for name in ROLES}
    db.add_all(users.values())
    db.flush()

    # Migrations initialize one default site. Reuse it in this NEW scratch DB;
    # an unexpected schema seed must fail instead of silently deleting a site.
    sites = list(db.scalars(select(ParkingSite)))
    if len(sites) > 1:
        raise ValueError("A fresh single-lot database unexpectedly contains multiple sites")
    site = sites[0] if sites else ParkingSite(is_active=True)
    site.name = "DEMO - Bãi đồ án một bãi"
    site.address = "Dữ liệu giả lập; không phải bãi xe hoặc giao dịch thực tế"
    site.is_active = True
    site.customer_booking_mode = "paid_packages"
    db.add(site)
    db.flush()
    for name in ("manager", "staff"):
        db.add(SiteMembership(site_id=site.id, user_id=users[name].id, role=name))

    kinds = {key: VehicleType(name=name, description="Dữ liệu DEMO") for key, name in
             (("bike", "Xe máy DEMO"), ("car", "Ô tô DEMO"))}
    db.add_all(kinds.values())
    db.flush()
    for key, amount in (("bike", 5000), ("car", 20000)):
        db.add(PriceConfig(vehicle_type_id=kinds[key].id, ticket_type="HOURLY", price=amount,
                           effective_date=(today - timedelta(days=90)).date(), is_active=True))
        db.add(SubscriptionPlan(site_id=site.id, name=f"DEMO {kinds[key].name} - 30 ngày",
                                vehicle_type_id=kinds[key].id, duration_days=30,
                                price=180000 if key == "bike" else 1200000, is_active=True))
        for product, minutes, price in (("hourly", 120, amount * 2), ("daily", 1440, amount * 8)):
            db.add(SubscriptionPlan(site_id=site.id, name=f"DEMO {kinds[key].name} - {minutes} phút",
                vehicle_type_id=kinds[key].id, product_kind=product, duration_minutes=minutes,
                duration_days=None, price=price, is_active=True))
    slots = {}
    for key, title, capacity, active in (("bike", "Xe máy", 24, True),
                                          ("car", "Ô tô", 12, True),
                                          ("reserve", "Dự phòng - ngừng sử dụng", 4, False)):
        zone = Zone(site_id=site.id, name=f"DEMO - {title}", capacity=capacity, is_active=True)
        db.add(zone)
        db.flush()
        slots[key] = [ParkingSlot(zone_id=zone.id, vehicle_type_id=kinds["car" if key == "reserve" else key].id,
                                  slot_name=f"DEMO-{key.upper()}-{i + 1:02}", is_active=active, is_occupied=False)
                      for i in range(capacity)]
        db.add_all(slots[key])
    db.flush()
    for direction in ("entry", "exit"):
        db.add(Camera(site_id=site.id, zone_id=slots["car"][0].zone_id, name=f"DEMO cổng {direction}",
                      direction=direction, retention_hours=24, is_active=True))

    monthly = {}
    owner = None
    for index, (label, days_from, days_to) in enumerate((("valid", -5, 24), ("near_expiry", -27, 2), ("expired", -40, -11))):
        customer = Customer(full_name=f"Khách DEMO - {label}", phone_number=f"DEMO-CUSTOMER-{index + 1}",
                            email=f"demo-{label}@example.invalid")
        db.add(customer)
        db.flush()
        vehicle = Vehicle(license_plate=f"DEMO-MONTH-{index + 1}", vehicle_type_id=kinds["bike"].id, customer_id=customer.id)
        db.add(vehicle)
        db.flush()
        # Complimentary examples keep monthly revenue honest until the paid
        # portal order is exercised. Expiry is date-based; expired != disabled.
        card = ParkingCard(code=f"DEMO-MONTH-{index + 1}", customer_id=customer.id, vehicle_id=vehicle.id)
        db.add(card)
        db.flush()
        monthly_pass = MonthlyPass(customer_id=customer.id, vehicle_id=vehicle.id, pass_code=f"DEMO-MONTH-{index + 1}",
                                   card_id=card.id,
                                   price=0, start_date=(today + timedelta(days=days_from)).date(),
                                   end_date=(today + timedelta(days=days_to)).date(), is_active=True,
                                   created_at=today + timedelta(days=days_from))
        db.add(monthly_pass)
        db.flush()
        PaymentService.record_receipt(db, "monthly_pass", monthly_pass.id, 0, None,
                                      method="demo", created_at=today + timedelta(days=days_from))
        monthly[label] = {"pass": monthly_pass, "vehicle": vehicle}
        if label == "valid":
            owner = customer
            db.add(PortalAccountLink(user_id=users["customer"].id, customer_id=customer.id,
                                    verified_by_id=users["admin"].id, verification="single_lot_demo_seed", created_at=now))
            db.add(PortalVehicleOwnership(customer_id=customer.id, vehicle_id=vehicle.id,
                                         approved_by_id=users["admin"].id, approved_at=now))

    visitor = Vehicle(license_plate="DEMO-CAR-VISITOR", vehicle_type_id=kinds["car"].id, customer_id=owner.id)
    db.add(visitor)
    db.flush()
    db.add(PortalVehicleOwnership(customer_id=owner.id, vehicle_id=visitor.id,
                                 approved_by_id=users["admin"].id, approved_at=now))
    history_slots = slots["bike"][:8] + slots["car"][:4]
    history_vehicles = [Vehicle(license_plate=f"DEMO-HISTORY-{i + 1:02}", vehicle_type_id=slot.vehicle_type_id)
                        for i, slot in enumerate(history_slots)]
    db.add_all(history_vehicles)
    db.flush()

    history_count = synthetic_revenue = 0
    first_day = today - timedelta(days=14)
    for day_offset in range(14):
        day = first_day + timedelta(days=day_offset)
        shift = CashShift(staff_id=users["staff"].id, site_id=site.id, status="open",
                          opening_cash=0, opened_at=day + timedelta(hours=6))
        db.add(shift)
        db.flush()
        daily_cash = 0
        for hour, volume in ((7, 3), (8, 10), (12, 4), (17, 12), (18, 8), (20, 3)):
            count = max(1, volume // 2) if day.weekday() >= 5 else volume
            for i in range(count):
                entered = day + timedelta(hours=hour, minutes=i)
                departed = entered + timedelta(minutes=35)
                vehicle = history_vehicles[i]
                fee = ParkingService(db).calculate_fee(vehicle.id, vehicle.vehicle_type_id, entered, departed)
                session = ParkingSession(id=str(uuid5(NAMESPACE_URL, f"parkingai:{PROFILE}:{entered.isoformat()}:{i}")),
                                         vehicle_id=vehicle.id, parking_slot_id=history_slots[i].id,
                                         check_in_time=entered, check_out_time=departed, parking_fee=fee, status="completed",
                                         staff_in_id=users["staff"].id, staff_out_id=users["staff"].id,
                                         image_in_url="demo://synthetic-history/single-lot",
                                         created_at=entered, updated_at=departed)
                db.add(session)
                db.flush()
                PaymentService.record_receipt(db, "parking_session", session.id, fee, users["staff"].id,
                                              method="cash", created_at=departed)
                daily_cash += fee
                history_count += 1
        shift.status = "closed"
        shift.closed_at = day + timedelta(hours=21)
        shift.expected_cash = shift.counted_cash = daily_cash
        shift.difference = 0
        db.flush()
        synthetic_revenue += daily_cash

    for vehicle, slot, monthly_pass in ((monthly["valid"]["vehicle"], slots["bike"][23], monthly["valid"]["pass"]),
                                        (visitor, slots["car"][11], None)):
        slot.is_occupied = True
        entered = now - timedelta(minutes=20)
        active = ParkingSession(vehicle_id=vehicle.id, parking_slot_id=slot.id,
                                monthly_pass_id=monthly_pass.id if monthly_pass else None,
                                monthly_coverage_end=monthly_pass.end_date if monthly_pass else None,
                                check_in_time=entered, status="active", staff_in_id=users["staff"].id,
                                image_in_url="demo://seed-active/single-lot",
                                **resolve_check_in_billing_snapshot(db, vehicle.vehicle_type_id, entered))
        db.add(active)
        db.flush()
        db.add(PortalSessionGrant(parking_session_id=active.id, customer_id=owner.id))
    db.commit()
    return {"parkingai_demo": True, "synthetic_history": True, "profile": PROFILE, "single_site_id": site.id,
            "history_days": 14, "history_start": str(first_day.date()), "history_end": str((today - timedelta(days=1)).date()),
            "empty_period": {"period": "week", "anchor_date": str((first_day - timedelta(days=1)).date())},
            "synthetic_closed_sessions": history_count, "synthetic_cash_receipts": history_count,
            "complimentary_monthly_receipts": 3,
            "synthetic_cash_revenue": synthetic_revenue, "real_money_received": 0, "closed_cash_shifts": 14,
            "active_sessions": 2, "zones": 3, "total_slots": 40, "active_slots": 36, "available_slots": 34,
            "sites": [{"id": site.id, "name": site.name}], "usernames": list(credentials),
            "monthly_examples": {key: {"pass_code": row["pass"].pass_code, "end_date": str(row["pass"].end_date),
                                        "price": 0} for key, row in monthly.items()},
            "note": "Toàn bộ lượt xe và chứng từ tiền mặt là dữ liệu giả lập trong DB đồ án riêng. Không có tiền thật hoặc giao dịch ngân hàng."}


def create_single_lot_demo(database_path):
    from expansion.demo_seed import create_new_demo
    target = Path(database_path).expanduser().resolve()
    private_path = Path(str(target) + ".demo-credentials.json")
    if target.exists() or Path(str(target) + ".demo.json").exists() or private_path.exists():
        raise FileExistsError("Demo database, marker or credentials already exists; no files were changed")
    target.parent.mkdir(parents=True, exist_ok=True)
    credentials = {f"{role}_demo": secrets.token_urlsafe(24) for role in ROLES}
    private = {"database": str(target), "profile": PROFILE, "accounts": credentials,
               "note": "Mật khẩu DEMO cục bộ. Không commit, chia sẻ công khai hoặc dùng cho tài khoản thật."}
    # Exclusive creation both protects an earlier credential file and reserves
    # this profile while the scratch database is built. Mode 0600 on POSIX;
    # Windows inherits the user's directory ACL, as do other local artifacts.
    fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(private, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        def seed(db, now):
            details = _seed_rows(db, credentials, now)
            details["credentials_file"] = str(private_path)
            return details
        return create_new_demo(target, seed)
    except Exception:
        private_path.unlink(missing_ok=True)
        raise


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    # Backend's ambient connection cannot select a user's database. No key or
    # password is echoed and no AI client is enabled during bootstrap.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    os.environ["AI_ENABLED"] = "false"
    os.environ["GEMINI_API_KEY"] = ""
    try:
        print(json.dumps(create_single_lot_demo(args.database), ensure_ascii=False, indent=2))
    except (ValueError, FileExistsError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
