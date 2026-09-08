"""Explicit expansion migration helpers, called only on a disposable SQLite copy.

The payment rebuild changes one known CHECK and retains rows, extra columns,
indexes, triggers and foreign keys. It never rewrites sqlite_master directly.
"""
from __future__ import annotations

import re

from sqlalchemy import CheckConstraint, inspect, text

from core.clock import business_now


DEFAULT_SITE_NAME = "Bãi xe mặc định"
_OLD_METHOD = re.compile(
    r'CONSTRAINT\s+(?:"ck_payment_method"|ck_payment_method)\s+CHECK\s*\(\s*'
    r"method\s+IN\s*\(\s*'cash'\s*,\s*'transfer'\s*,\s*'legacy_unknown'\s*\)\s*\)",
    re.IGNORECASE,
)


def _signature(sql: str) -> str:
    # SQL keywords are case-insensitive; quoted enum values are not.
    parts = re.split(r"('(?:''|[^'])*')", sql)
    return "".join(part if index % 2 else "".join(part.lower().split()) for index, part in enumerate(parts))


def migrate_sqlite_payment_demo(target_engine) -> None:
    """Upgrade only the known pre-demo payment contract in a staging database."""
    inspector = inspect(target_engine)
    if not inspector.has_table("payments"):
        return
    checks = {item["name"]: item["sqltext"] for item in inspector.get_check_constraints("payments")}
    method = _signature(checks.get("ck_payment_method", ""))
    current = "methodin('cash','transfer','legacy_unknown','demo')"
    old = "methodin('cash','transfer','legacy_unknown')"
    if method not in (old, current):
        raise RuntimeError("payments.ck_payment_method không đúng schema đã biết; không tự sửa constraint lạ")
    demo_check = checks.get("ck_payment_demo_unassigned")
    if demo_check is not None and _signature(demo_check) != "method!='demo'orshift_idisnull":
        raise RuntimeError("payments.ck_payment_demo_unassigned sai định nghĩa")
    if method == current and demo_check is not None:
        return

    raw = target_engine.raw_connection()
    try:
        raw.commit()
        foreign_keys = raw.execute("PRAGMA foreign_keys").fetchone()[0]
        legacy_alter = raw.execute("PRAGMA legacy_alter_table").fetchone()[0]
        raw.execute("PRAGMA foreign_keys=OFF")
        # References in external triggers remain pointed at the final table
        # while its replacement briefly uses the staging name.
        raw.execute("PRAGMA legacy_alter_table=ON")
        raw.execute("BEGIN IMMEDIATE")
        try:
            original = raw.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='payments'").fetchone()[0]
            replacement = original
            if method == old:
                replacement, count = _OLD_METHOD.subn(
                    "CONSTRAINT ck_payment_method CHECK (method IN ('cash', 'transfer', 'legacy_unknown', 'demo'))",
                    replacement,
                )
                if count != 1:
                    raise RuntimeError("Không nhận diện duy nhất payment CHECK để migration an toàn")
            if demo_check is None:
                end = replacement.rfind(")")
                replacement = replacement[:end] + ", CONSTRAINT ck_payment_demo_unassigned CHECK (method != 'demo' OR shift_id IS NULL)" + replacement[end:]
            replacement, count = re.subn(
                r'^CREATE\s+TABLE\s+(?:"payments"|payments)\s*\(',
                'CREATE TABLE "_payments_expansion_candidate" (', replacement,
                count=1, flags=re.IGNORECASE,
            )
            if count != 1:
                raise RuntimeError("Không nhận diện bảng payments để migration an toàn")
            objects = raw.execute("SELECT sql FROM sqlite_master WHERE tbl_name='payments' AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type, name").fetchall()
            columns = [row[1] for row in raw.execute("PRAGMA table_xinfo(payments)") if row[6] == 0]
            quoted = ", ".join('"' + name.replace('"', '""') + '"' for name in columns)
            count_before = raw.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
            raw.execute(replacement)
            raw.execute(f'INSERT INTO "_payments_expansion_candidate" ({quoted}) SELECT {quoted} FROM payments')
            count_after = raw.execute('SELECT COUNT(*) FROM "_payments_expansion_candidate"').fetchone()[0]
            if count_before != count_after:
                raise RuntimeError("Số dòng payments thay đổi trong migration")
            raw.execute("DROP TABLE payments")
            raw.execute('ALTER TABLE "_payments_expansion_candidate" RENAME TO payments')
            for (statement,) in objects:
                raw.execute(statement)
            errors = raw.execute("PRAGMA foreign_key_check").fetchall()
            if errors:
                raise RuntimeError(f"Payment migration vi phạm foreign key: {errors}")
            raw.commit()
        except BaseException:
            raw.rollback()
            raise
        finally:
            raw.execute(f"PRAGMA legacy_alter_table={int(legacy_alter)}")
            raw.execute(f"PRAGMA foreign_keys={int(foreign_keys)}")
    finally:
        raw.close()


def backfill_legacy_sites(connection) -> None:
    """Assign legacy zones once; identity/ownership is never inferred."""
    sites = connection.execute(text("SELECT id FROM parking_sites ORDER BY id")).scalars().all()
    initial = not sites
    if initial:
        connection.execute(text("INSERT INTO parking_sites (name,address,is_active,created_at) VALUES (:name,'',true,:now)"), {"name": DEFAULT_SITE_NAME, "now": business_now()})
        sites = connection.execute(text("SELECT id FROM parking_sites")).scalars().all()
    unassigned = connection.execute(text("SELECT id FROM zones WHERE site_id IS NULL ORDER BY id LIMIT 1")).first()
    if unassigned and len(sites) != 1:
        raise RuntimeError("Có nhiều bãi xe nhưng khu vực chưa được gán site_id; cần phân loại khu vực trước rollout")
    if len(sites) == 1:
        connection.execute(text("UPDATE zones SET site_id=:site WHERE site_id IS NULL"), {"site": sites[0]})
    if initial:
        connection.execute(text("""
            INSERT INTO site_memberships (site_id,user_id,role)
            SELECT :site,u.id,r.name FROM users u JOIN roles r ON r.id=u.role_id
            WHERE r.name IN ('staff','manager')
        """), {"site": sites[0]})


def validate_expansion_checks(target_engine, metadata) -> None:
    """CHECK definitions for newly introduced tables must survive legacy rollout."""
    inspector = inspect(target_engine)
    for table in metadata.sorted_tables:
        # Legacy tables predate CHECKs and enforce their equivalent rules
        # with registered triggers. New expansion/payment checks are strict.
        if table.name != "payments" and table.name not in EXPANSION_TABLES:
            continue
        actual = {item["name"]: _signature(item["sqltext"]) for item in inspector.get_check_constraints(table.name)}
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                if actual.get(constraint.name) != _signature(str(constraint.sqltext)):
                    raise RuntimeError(f"Constraint {table.name}.{constraint.name} thiếu hoặc sai định nghĩa")


def validate_zone_site_assignment(connection) -> None:
    """Reject ambiguous operational data without repairing it during readiness.

    Zero/one-site legacy databases can still be assigned deterministically by
    explicit rollout. With multiple sites, even closed-site history prevents
    inferring which site owns an unassigned zone.
    """
    orphan = connection.execute(text("""
        SELECT id FROM zones WHERE site_id IS NULL
          AND (SELECT COUNT(*) FROM parking_sites) > 1
        ORDER BY id LIMIT 1
    """)).first()
    if orphan:
        raise RuntimeError(f"Khu vực chưa được gán site_id trong hệ thống nhiều bãi: zone_id={orphan[0]}")


EXPANSION_TABLES = frozenset({
    "parking_sites", "site_memberships", "parking_reservations", "guaranteed_allocations",
    "site_waitlist", "organizations", "organization_memberships", "fleet_vehicles",
    "portal_account_links", "portal_link_requests", "portal_vehicle_requests", "portal_vehicle_ownerships",
    "portal_session_grants", "subscription_plans", "portal_orders", "portal_payment_events",
    "portal_notifications", "portal_refund_requests", "vision_cameras", "vision_observations",
})
