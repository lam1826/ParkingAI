"""Explicit known-schema upgrades, on the rollout helper's private candidate only."""
import re

from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.schema import CreateColumn
from sqlalchemy.dialects import sqlite

from core.billing_guards import BILLING_SQLITE_GUARDS
from expansion_demo_guards import DEMO_SQLITE_GUARD_SQL
from expansion.timed_parking_guards import TIMED_SQLITE_GUARDS, PRE_COMPLETED_HOLD_GUARDS
from expansion.site_models import PRE_COMPLETED_RESERVATION_GUARDS

PRE_TIMED_TRIGGER_SQL = {
    **PRE_COMPLETED_RESERVATION_GUARDS,
    **PRE_COMPLETED_HOLD_GUARDS,
    "trg_payment_prepaid_source": TIMED_SQLITE_GUARDS["trg_payment_prepaid_source"].replace(
        " OR (o.payment_mode='payos' AND NEW.method='transfer' AND NEW.collected_by_id IS NULL)", ""),
    "trg_parking_sessions_billing_snapshot_insert": BILLING_SQLITE_GUARDS["trg_parking_sessions_billing_snapshot_insert"].replace(
        "NEW.billing_policy_version IN ('entry-v1','prepaid-window-v1')", "NEW.billing_policy_version = 'entry-v1'"),
    "trg_payment_demo_boundary": DEMO_SQLITE_GUARD_SQL.replace("source_type NOT IN ('monthly_pass','portal_order')", "source_type!='monthly_pass'"),
}

_OLD_CHECKS = {
    ("portal_orders", "ck_portal_order_mode"): "payment_mode IN ('demo','manual')",
    ("subscription_plans", "ck_portal_plan_duration"): "duration_days >= 1 AND duration_days <= 366",
    ("portal_orders", "ck_portal_order_fulfilled"): "status NOT IN ('fulfilled','refunded') OR (monthly_pass_id IS NOT NULL AND receipt_id IS NOT NULL)",
    ("payments", "ck_payment_source"): ("source_type IN ('parking_session', 'monthly_pass')",
        "source_type IN ('parking_session', 'monthly_pass', 'portal_order')"),
}
ADDITIONS = {
    "parking_sites": ("customer_booking_mode",),
    "subscription_plans": ("product_kind", "duration_minutes"),
    "portal_orders": ("product_kind", "plan_name", "duration_days", "duration_minutes", "start_at", "end_at",
        "arrival_deadline", "zone_id", "slot_id", "requested_zone_id", "rate_config_id", "rate_ticket_type",
        "rate_unit_price", "rate_effective_date", "timed_pass_id"),
    "parking_reservations": ("order_id",),
    "parking_sessions": ("timed_pass_id", "prepaid_start_at", "prepaid_end_at"),
}


def _replace_check(sql, name, expression):
    """Locate a named CHECK and walk balanced SQL parentheses (including strings)."""
    match = re.search(r'CONSTRAINT\s+"?' + re.escape(name) + r'"?\s+CHECK\s*\(', sql, re.I)
    if match is None:
        at = sql.rfind(")")
        return sql[:at] + f", CONSTRAINT {name} CHECK ({expression})" + sql[at:]
    depth, quoted, pos = 1, False, match.end()
    while depth:
        if pos >= len(sql):
            raise RuntimeError("CHECK không cân bằng; từ chối schema không nhận diện")
        char = sql[pos]
        if char == "'":
            if quoted and pos + 1 < len(sql) and sql[pos + 1] == "'":
                pos += 2
                continue
            quoted = not quoted
        elif not quoted:
            depth += (char == "(") - (char == ")")
        pos += 1
    return sql[:match.start()] + f"CONSTRAINT {name} CHECK ({expression})" + sql[pos:]


def migrate_timed_parking(target_engine):
    from database import Base
    from expansion_rollout import _signature
    inspector = inspect(target_engine)
    existing = set(inspector.get_table_names())
    rebuilds = {}
    # Validate before starting mutation. Unknown named constraints are never replaced.
    for table in ("subscription_plans", "portal_orders", "payments"):
        if table not in existing:
            continue
        actual = {item["name"]: item["sqltext"] for item in inspector.get_check_constraints(table)}
        expected = {c.name: str(c.sqltext) for c in Base.metadata.tables[table].constraints if isinstance(c, CheckConstraint)}
        replacements = {}
        for name, expression in expected.items():
            if name not in {key[1] for key in _OLD_CHECKS if key[0] == table} and name not in {"ck_portal_order_product", "ck_portal_order_timed"}:
                continue
            old = actual.get(name)
            if old is not None and _signature(old) == _signature(expression):
                continue
            allowed = _OLD_CHECKS.get((table, name))
            allowed_values = allowed if isinstance(allowed, tuple) else (allowed,)
            if old is not None and not any(value is not None and _signature(old) == _signature(value) for value in allowed_values):
                raise RuntimeError(f"Không tự sửa CHECK lạ: {table}.{name}")
            if old is None and allowed is not None:
                raise RuntimeError(f"Thiếu CHECK nền: {table}.{name}")
            replacements[name] = expression
        if replacements or table == "subscription_plans" and not next(c for c in inspector.get_columns(table) if c["name"] == "duration_days")["nullable"]:
            rebuilds[table] = replacements
    raw = target_engine.raw_connection()
    try:
        raw.commit()
        fk = raw.execute("PRAGMA foreign_keys").fetchone()[0]
        legacy = raw.execute("PRAGMA legacy_alter_table").fetchone()[0]
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("PRAGMA legacy_alter_table=ON")
        raw.execute("BEGIN IMMEDIATE")
        try:
            for table, names in ADDITIONS.items():
                if table not in existing:
                    continue
                columns = {row[1] for row in raw.execute(f'PRAGMA table_info("{table}")')}
                for name in names:
                    if name not in columns:
                        column = Base.metadata.tables[table].c[name]
                        definition = str(CreateColumn(column).compile(dialect=sqlite.dialect()))
                        for reference in column.foreign_keys:
                            parent = reference.column
                            definition += f' REFERENCES "{parent.table.name}" ("{parent.name}")'
                        # ALTER cannot add UNIQUE; explicit indexes below enforce reverse links.
                        raw.execute(f'ALTER TABLE "{table}" ADD COLUMN {definition}')
            for table, replacements in rebuilds.items():
                original = raw.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
                ddl = original
                for name, expression in replacements.items():
                    ddl = _replace_check(ddl, name, expression)
                if table == "subscription_plans":
                    ddl = re.sub(r'(\bduration_days\s+INTEGER)\s+NOT\s+NULL', r'\1', ddl, flags=re.I)
                candidate = "_timed_" + table
                ddl, count = re.subn(r'^CREATE\s+TABLE\s+"?' + table + r'"?\s*\(', f'CREATE TABLE "{candidate}" (', ddl, count=1, flags=re.I)
                if count != 1:
                    raise RuntimeError("Không nhận diện CREATE TABLE để migration")
                objects = raw.execute("SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL ORDER BY type,name", (table,)).fetchall()
                columns = [row[1] for row in raw.execute(f'PRAGMA table_xinfo("{table}")') if row[6] == 0]
                quoted = ",".join('"' + name.replace('"', '""') + '"' for name in columns)
                before = raw.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                raw.execute(ddl)
                raw.execute(f'INSERT INTO "{candidate}" ({quoted}) SELECT {quoted} FROM "{table}"')
                if before != raw.execute(f'SELECT COUNT(*) FROM "{candidate}"').fetchone()[0]:
                    raise RuntimeError("Số dòng thay đổi trong migration vé giờ/ngày")
                raw.execute(f'DROP TABLE "{table}"')
                raw.execute(f'ALTER TABLE "{candidate}" RENAME TO "{table}"')
                for (statement,) in objects:
                    raw.execute(statement)
            for table, column in (("portal_orders", "timed_pass_id"), ("parking_sessions", "timed_pass_id"), ("parking_reservations", "order_id")):
                if table in existing:
                    raw.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_{column}" ON "{table}" ("{column}")')
            for name, old in PRE_TIMED_TRIGGER_SQL.items():
                row = raw.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
                if row and _signature(row[0].replace("IF NOT EXISTS ", "")) == _signature(old.replace("IF NOT EXISTS ", "")):
                    raw.execute(f'DROP TRIGGER "{name}"')
            if raw.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("Foreign key không hợp lệ sau migration vé giờ/ngày")
            raw.commit()
        except BaseException:
            raw.rollback()
            raise
        finally:
            raw.execute(f"PRAGMA legacy_alter_table={int(legacy)}")
            raw.execute(f"PRAGMA foreign_keys={int(fk)}")
    finally:
        raw.close()


def validate_timed_parking(connection):
    invalid = connection.exec_driver_sql("""SELECT o.id FROM portal_orders o WHERE o.product_kind!='monthly'
        AND o.status IN ('fulfilled','refunded') AND NOT EXISTS (
          SELECT 1 FROM timed_parking_passes t JOIN payments p ON p.id=o.receipt_id
          WHERE t.id=o.timed_pass_id AND t.order_id=o.id AND p.source_type='portal_order'
          AND p.source_id=o.id AND p.kind='receipt' AND p.amount=o.amount AND p.site_id=o.site_id) LIMIT 1""").first()
    if invalid:
        raise RuntimeError("Đơn giờ/ngày thiếu quyền hoặc chứng từ hợp lệ")
    invalid = connection.exec_driver_sql("""SELECT t.id FROM timed_parking_passes t JOIN portal_orders o ON o.id=t.order_id
        WHERE o.status NOT IN ('fulfilled','refunded') OR o.timed_pass_id IS NOT t.id
        OR t.vehicle_id!=o.vehicle_id OR t.customer_id!=o.customer_id OR t.site_id!=o.site_id
        OR t.slot_id!=o.slot_id OR t.start_at!=o.start_at OR t.end_at!=o.end_at OR t.amount!=o.amount
        OR t.rate_config_id!=o.rate_config_id OR t.rate_unit_price!=o.rate_unit_price
        OR (t.status='consumed' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.id=t.session_id AND s.timed_pass_id=t.id))
        LIMIT 1""").first()
    if invalid:
        raise RuntimeError("Quyền giờ/ngày không khớp đơn hoặc lượt sử dụng")
