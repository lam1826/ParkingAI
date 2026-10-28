"""Deploy step of review 28/10/2026 R2-01: release declarations left from before the fix.

Before the fix, another account could declare a plate already verified to a
customer profile. Such a "foreign" row is never consumed by, matched to or
shown the owner's car, but while it lives (until its arrival deadline, at most
30 days + 15 minutes) it still blocks the owner's own bookings of the plate.
Run once before rollout, in the maintenance window:

    cd backend
    ../.venv/Scripts/python.exe -m expansion.release_foreign_declarations --database <sqlite path or URL>
    ../.venv/Scripts/python.exe -m expansion.release_foreign_declarations --database <...> --apply

The default is a read-only count. ``--apply`` runs ``release_foreign`` for each
such vehicle under ``lock_identity``, in one maintenance transaction. Only
counts and the ids of skipped vehicles (a plate legacy data spells as several
vehicles, for staff to merge first) are printed: no plate, account or time.
Never run at startup.
Backend modules are imported lazily, after the command has isolated the
ambient settings (the same pattern as ``expansion.single_lot_seed``).
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path


def _foreign_rows(now):
    """(vehicle, declaration) pairs: a live declaration of a plate verified to a profile, by an account not linked to it."""
    from sqlalchemy import exists, select
    from core.vehicle_identity import identity_expression
    from expansion.declared_bookings import live_declared
    from expansion.portal_models import PortalAccountLink
    from expansion.simplified_customer_models import DeclaredParkingReservation as Booking
    from models.vehicle import Vehicle
    linked = exists().where(PortalAccountLink.customer_id == Vehicle.customer_id, PortalAccountLink.user_id == Booking.user_id)
    return (select(Vehicle.id, Booking.id)
        .join(Booking, Booking.normalized_plate == identity_expression(Vehicle.license_plate))
        .where(Vehicle.customer_id.is_not(None), live_declared(now), ~linked))


def _now(now):
    from expansion import declared_bookings
    return declared_bookings.server_now() if now is None else now


def foreign_counts(db, now=None):
    """Read-only: how many foreign live declarations exist, and on how many vehicles.

    A plate that legacy data spells as several vehicles pairs one declaration
    with each of them, so both numbers count distinct rows.
    """
    pairs = db.execute(_foreign_rows(_now(now))).all()
    return {"foreign_declarations": len({booking for _, booking in pairs}),
            "vehicles": len({vehicle for vehicle, _ in pairs})}


def release_foreign_declarations(db, now=None):
    """Release every foreign live declaration; the caller commits (one maintenance transaction).

    Identity locks are taken in plate order, each before its vehicle is re-read,
    as at every other release point; no slot lock is taken. A plate that now
    matches several legacy vehicles is skipped: staff must check it first, so
    the skipped vehicle ids (no plate or account) are returned for that check.
    """
    from fastapi import HTTPException
    from sqlalchemy import select
    from core.vehicle_identity import canonical_identity, lock_identity, resolve_vehicle
    from expansion.declared_bookings import release_foreign
    from models.vehicle import Vehicle
    now = _now(now)
    counts = foreign_counts(db, now)
    candidates = {vehicle_id for vehicle_id, _ in db.execute(_foreign_rows(now)).all()}
    vehicles = db.scalars(select(Vehicle).where(Vehicle.id.in_(candidates))).all() if candidates else []
    released, skipped = 0, []
    for vehicle in sorted(vehicles, key=lambda row: (canonical_identity(row.license_plate), row.id)):
        lock_identity(db, vehicle.vehicle_type_id, vehicle.license_plate)
        try:
            current = resolve_vehicle(db, vehicle.license_plate)
        except HTTPException:
            current = None
        if current is None or current.id != vehicle.id or current.customer_id is None:
            skipped.append(vehicle.id)
            continue
        released += release_foreign(db, current, now)
    return {**counts, "released": released, "skipped_vehicles": len(skipped), "skipped_vehicle_ids": sorted(skipped)}


def _database_url(value):
    if "://" in value:
        return value
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError("Không tìm thấy file database; lệnh không tạo database mới.")
    return f"sqlite:///{path.as_posix()}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Đếm (mặc định) hoặc hủy (--apply) đặt trước của tài khoản khác "
        "trên biển số đã xác minh cho hồ sơ khách, còn lại từ trước bản sửa R2-01.")
    parser.add_argument("--database", required=True, help="Đường dẫn file SQLite hoặc URL database")
    parser.add_argument("--apply", action="store_true", help="Hủy các đặt trước đó trong một giao dịch bảo trì")
    arguments = parser.parse_args(argv)
    try:
        url = _database_url(arguments.database)
    except ValueError as exc:
        parser.exit(2, f"{exc}\n")
    from sqlalchemy.orm import Session
    from database import create_database_engine
    import models  # noqa: F401 - register every mapping used by the joins
    engine = create_database_engine(url)
    try:
        with Session(engine) as db:
            if arguments.apply:
                result = release_foreign_declarations(db)
                db.commit()
            else:
                result = foreign_counts(db)
                db.rollback()
    finally:
        engine.dispose()
    print(json.dumps({**result, "applied": arguments.apply}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    # Backend's ambient connection never selects the operator's database, and
    # no key from the environment is needed to count or release rows.
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["SECRET_KEY"] = secrets.token_hex(32)
    os.environ["AI_ENABLED"] = "false"
    os.environ["GEMINI_API_KEY"] = ""
    raise SystemExit(main())
