"""Database invariants shared by fresh schemas and explicit candidate rollout."""
import re
from sqlalchemy import DDL, event
from database import Base

TIMED_SQLITE_GUARDS = {}
_postgres = []


def guard(name, table, operation, condition, message):
    TIMED_SQLITE_GUARDS[name] = (f"CREATE TRIGGER IF NOT EXISTS {name} BEFORE {operation} ON {table} "
        f"FOR EACH ROW WHEN {condition} BEGIN SELECT RAISE(ABORT, '{message}'); END")
    predicate = condition.replace("strftime('%Y-%m-%d %H:%M:%f','now','+7 hours')", "(clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')")
    predicate = re.sub(r"\bIS NOT (?!NULL\b)([A-Za-z_][A-Za-z_.]*)", r"IS DISTINCT FROM \1", predicate)
    predicate = re.sub(r"\bIS (?!NULL\b|NOT\b|DISTINCT\b)([A-Za-z_][A-Za-z_.]*)", r"IS NOT DISTINCT FROM \1", predicate)
    predicate = re.sub(r"\.(is_active|is_occupied)=1\b", r".\1 IS TRUE", predicate)
    predicate = re.sub(r"\.(is_active|is_occupied)=0\b", r".\1 IS FALSE", predicate)
    if predicate == "1":
        predicate = "true"
    locks = ""
    if operation == "INSERT" and table in {"parking_capacity_holds", "parking_reservations", "guaranteed_allocations"}:
        locks = ("PERFORM 1 FROM vehicles WHERE id=NEW.vehicle_id FOR NO KEY UPDATE; "
            "PERFORM 1 FROM vehicle_types WHERE id=(SELECT vehicle_type_id FROM vehicles WHERE id=NEW.vehicle_id) FOR SHARE; "
            "PERFORM 1 FROM parking_slots WHERE id=NEW.slot_id FOR UPDATE;")
    _postgres.append(f"""CREATE OR REPLACE FUNCTION {name}_fn() RETURNS trigger AS $$
BEGIN
    {locks}
    IF {predicate} THEN RAISE EXCEPTION '{message}' USING ERRCODE='23514'; END IF;
    RETURN {'OLD' if operation == 'DELETE' else 'NEW'};
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER {name} BEFORE {operation} ON {table} FOR EACH ROW EXECUTE FUNCTION {name}_fn();
""")


def changed(fields):
    return " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in fields)


_clock = "strftime('%Y-%m-%d %H:%M:%f','now','+7 hours')"
_live = f"h.status='held' AND h.expires_at>{_clock}"
_identity = "id order_id site_id slot_id customer_id vehicle_id start_at end_at created_at".split()
_order_snapshot = ("id user_id customer_id vehicle_id plan_id site_id amount start_date end_date payment_mode "
    "idempotency_key demo_token expires_at created_at product_kind plan_name duration_days duration_minutes "
    "start_at end_at arrival_deadline zone_id slot_id requested_zone_id rate_config_id rate_ticket_type "
    "rate_unit_price rate_effective_date").split()
for operation in ("INSERT", "UPDATE"):
    guard(f"trg_site_booking_mode_{operation.lower()}", "parking_sites", operation,
        "NEW.customer_booking_mode NOT IN ('legacy','paid_packages')", "unknown customer booking mode")
guard("trg_timed_order_insert", "portal_orders", "INSERT", "NEW.product_kind!='monthly' AND NOT COALESCE(("
    "NEW.status='pending' AND NEW.start_at IS NOT NULL AND NEW.end_at>NEW.start_at "
    "AND NEW.arrival_deadline>=NEW.start_at AND NEW.arrival_deadline<=NEW.end_at "
    "AND NEW.expires_at<=NEW.arrival_deadline AND NEW.rate_unit_price>=0 AND NEW.rate_unit_price<=9007199254740991 "
    "AND NEW.rate_ticket_type IN ('HOURLY','DAILY') AND NEW.rate_config_id>0 AND NEW.rate_effective_date IS NOT NULL "
    "AND NEW.duration_minutes>0 AND NEW.plan_name IS NOT NULL AND NEW.slot_id IS NOT NULL AND NEW.zone_id IS NOT NULL "
    "AND NEW.timed_pass_id IS NULL AND NEW.receipt_id IS NULL AND NEW.monthly_pass_id IS NULL), false)", "timed order snapshot invalid")
guard("trg_timed_order_price_source", "portal_orders", "INSERT", "NEW.product_kind!='monthly' AND NOT EXISTS ("
    "SELECT 1 FROM subscription_plans p JOIN vehicles v ON v.id=NEW.vehicle_id JOIN price_configs r ON r.id=NEW.rate_config_id "
    "WHERE p.id=NEW.plan_id AND p.is_active=1 AND p.site_id=NEW.site_id AND p.vehicle_type_id=v.vehicle_type_id "
    "AND p.name=NEW.plan_name AND p.price=NEW.amount AND p.product_kind=NEW.product_kind AND p.duration_minutes=NEW.duration_minutes "
    "AND r.vehicle_type_id=v.vehicle_type_id AND r.is_active=1 AND r.price=NEW.rate_unit_price "
    "AND r.ticket_type=NEW.rate_ticket_type AND r.effective_date=NEW.rate_effective_date)", "timed order price source invalid")
guard("trg_timed_order_immutable", "portal_orders", "UPDATE", changed(_order_snapshot) +
    " OR (OLD.status IN ('fulfilled','refunded') AND (NEW.timed_pass_id IS NOT OLD.timed_pass_id "
    "OR NEW.monthly_pass_id IS NOT OLD.monthly_pass_id OR NEW.receipt_id IS NOT OLD.receipt_id "
    "OR NEW.status NOT IN ('fulfilled','refunded'))) OR (OLD.status='refunded' AND NEW.status!='refunded')",
    "portal order snapshot immutable")
guard("trg_timed_order_delete", "portal_orders", "DELETE", "1", "portal order history cannot be deleted")
guard("trg_timed_order_replace", "portal_orders", "INSERT", "EXISTS (SELECT 1 FROM portal_orders WHERE id=NEW.id)", "portal order snapshot immutable")
guard("trg_timed_order_fulfilled", "portal_orders", "UPDATE", "NEW.product_kind!='monthly' AND NEW.status IN ('fulfilled','refunded') AND NOT EXISTS ("
    "SELECT 1 FROM timed_parking_passes t JOIN payments p ON p.id=NEW.receipt_id WHERE t.id=NEW.timed_pass_id "
    "AND t.order_id=NEW.id AND p.source_type='portal_order' AND p.source_id=NEW.id AND p.kind='receipt' "
    "AND p.amount=NEW.amount AND p.site_id=NEW.site_id)", "paid order requires ticket and receipt")
guard("trg_capacity_hold_insert", "parking_capacity_holds", "INSERT",
    "NEW.status!='held' OR NEW.reservation_id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM portal_orders o "
    "JOIN parking_slots s ON s.id=o.slot_id JOIN zones z ON z.id=s.zone_id JOIN parking_sites p ON p.id=z.site_id "
    "JOIN vehicles v ON v.id=o.vehicle_id JOIN vehicle_types t ON t.id=v.vehicle_type_id WHERE o.id=NEW.order_id "
    "AND o.status='pending' AND o.product_kind IN ('hourly','daily') AND o.slot_id=NEW.slot_id "
    "AND o.site_id=NEW.site_id AND o.customer_id=NEW.customer_id AND o.vehicle_id=NEW.vehicle_id "
    "AND o.start_at=NEW.start_at AND o.end_at=NEW.end_at AND o.expires_at=NEW.expires_at "
    "AND v.customer_id=o.customer_id AND s.vehicle_type_id=v.vehicle_type_id AND t.is_active=1 "
    "AND s.is_active=1 AND z.is_active=1 AND p.is_active=1 AND s.is_occupied=0) "
    f"OR EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND {_live} "
    "AND h.start_at<NEW.end_at AND h.end_at>NEW.start_at) "
    "OR EXISTS (SELECT 1 FROM parking_sessions s WHERE s.parking_slot_id=NEW.slot_id AND s.status IN ('active','checking_out')) "
    "OR EXISTS (SELECT 1 FROM parking_reservations r WHERE r.slot_id=NEW.slot_id AND r.status IN ('confirmed','arrived') AND r.start_at<NEW.end_at AND r.end_at>NEW.start_at) "
    "OR EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.slot_id=NEW.slot_id AND a.status='active' AND a.start_at<NEW.end_at AND a.end_at>NEW.start_at)",
    "capacity hold source or overlap invalid")
guard("trg_capacity_hold_update", "parking_capacity_holds", "UPDATE",
    changed(_identity + ["expires_at"]) + " OR (OLD.status!='held' AND NEW.status!=OLD.status) "
    "OR (NEW.reservation_id IS NOT OLD.reservation_id AND (OLD.status!='held' OR NEW.status!='converted')) "
    "OR (NEW.status='converted' AND NOT EXISTS (SELECT 1 FROM parking_reservations r WHERE r.id=NEW.reservation_id AND r.order_id=NEW.order_id))",
    "capacity hold immutable or terminal")
for table in ("parking_capacity_holds", "timed_parking_passes"):
    guard(f"trg_{table}_delete", table, "DELETE", "1", "prepaid history cannot be deleted")
    guard(f"trg_{table}_replace", table, "INSERT", f"EXISTS (SELECT 1 FROM {table} WHERE id=NEW.id)", "prepaid history cannot be replaced")

_pass_fields = _identity + "reservation_id vehicle_type_id arrival_deadline amount rate_config_id rate_ticket_type rate_unit_price rate_effective_date".split()
_ticket_match = " AND ".join(f"o.{field}=NEW.{field}" for field in
    "site_id slot_id customer_id vehicle_id start_at end_at arrival_deadline amount rate_config_id rate_ticket_type rate_unit_price rate_effective_date".split())
guard("trg_timed_pass_insert", "timed_parking_passes", "INSERT", "NEW.status!='ready' OR NEW.session_id IS NOT NULL OR NOT EXISTS ("
    "SELECT 1 FROM portal_orders o JOIN parking_reservations r ON r.order_id=o.id JOIN vehicles v ON v.id=o.vehicle_id "
    "WHERE o.id=NEW.order_id AND r.id=NEW.reservation_id AND r.status='confirmed' AND o.status IN ('pending','review') "
    f"AND v.vehicle_type_id=NEW.vehicle_type_id AND {_ticket_match})", "prepaid ticket source invalid")
guard("trg_timed_pass_update", "timed_parking_passes", "UPDATE", changed(_pass_fields) +
    " OR (OLD.status!='ready' AND NEW.status!=OLD.status) OR (NEW.session_id IS NOT OLD.session_id AND (OLD.status!='ready' OR NEW.status!='consumed')) "
    "OR (NEW.status='consumed' AND NOT EXISTS (SELECT 1 FROM parking_sessions s WHERE s.id=NEW.session_id AND s.timed_pass_id=NEW.id))",
    "prepaid ticket immutable or consumed")

for table in ("parking_reservations", "guaranteed_allocations"):
    exclude = "AND h.order_id IS NOT NEW.order_id " if table == "parking_reservations" else ""
    guard(f"trg_{table}_capacity_hold", table, "INSERT",
        f"EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.slot_id AND {_live} {exclude}"
        "AND h.start_at<NEW.end_at AND h.end_at>NEW.start_at)", "slot has a live payment hold")

guard("trg_reservation_order_identity", "parking_reservations", "UPDATE", "NEW.order_id IS NOT OLD.order_id", "reservation order immutable")
guard("trg_reservation_paid_source", "parking_reservations", "INSERT", "NEW.order_id IS NOT NULL AND NOT EXISTS ("
    "SELECT 1 FROM parking_capacity_holds h JOIN portal_orders o ON o.id=h.order_id WHERE h.order_id=NEW.order_id "
    f"AND {_live} AND o.status IN ('pending','review') AND h.slot_id=NEW.slot_id AND h.site_id=NEW.site_id "
    "AND h.vehicle_id=NEW.vehicle_id AND h.customer_id=NEW.customer_id AND h.start_at=NEW.start_at AND h.end_at=NEW.end_at "
    "AND o.arrival_deadline=NEW.arrival_deadline AND o.user_id=NEW.created_by_id)", "paid reservation requires live matching hold")
_staff = ("EXISTS (SELECT 1 FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=NEW.created_by_id AND u.is_active=1 "
    "AND (r.name='admin' OR (r.name IN ('manager','staff') AND EXISTS (SELECT 1 FROM site_memberships m WHERE m.user_id=u.id AND m.site_id=NEW.site_id))))")
_allocation = ("EXISTS (SELECT 1 FROM guaranteed_allocations a WHERE a.status='active' AND a.site_id=NEW.site_id "
    "AND a.vehicle_id=NEW.vehicle_id AND a.customer_id=NEW.customer_id AND a.start_at<=NEW.start_at AND a.end_at>=NEW.end_at")
for table in ("parking_reservations", "site_waitlist"):
    allow_order = " AND NEW.order_id IS NULL" if table == "parking_reservations" else ""
    allocation = _allocation + (" AND a.slot_id=NEW.slot_id" if table == "parking_reservations" else "") + ")"
    guard(f"trg_{table}_paid_booking_mode", table, "INSERT", "EXISTS (SELECT 1 FROM parking_sites p WHERE p.id=NEW.site_id AND p.customer_booking_mode='paid_packages')"
        f"{allow_order} AND NOT {_staff} AND NOT {allocation}", "customer booking requires a paid package")

_prepaid_fields = ["timed_pass_id", "prepaid_start_at", "prepaid_end_at"]
guard("trg_session_prepaid_immutable", "parking_sessions", "UPDATE", changed(_prepaid_fields), "session prepaid window immutable")
_session_match = " AND ".join(f"t.{field}=NEW.{field}" for field in "vehicle_id rate_config_id rate_ticket_type rate_unit_price rate_effective_date".split())
guard("trg_session_prepaid_source", "parking_sessions", "INSERT",
    "(NEW.billing_policy_version='prepaid-window-v1' AND (NEW.timed_pass_id IS NULL OR NEW.monthly_pass_id IS NOT NULL OR NOT EXISTS ("
    "SELECT 1 FROM timed_parking_passes t JOIN portal_orders o ON o.id=t.order_id JOIN parking_reservations r ON r.id=t.reservation_id "
    "JOIN vehicles v ON v.id=t.vehicle_id JOIN payments p ON p.id=o.receipt_id WHERE t.id=NEW.timed_pass_id "
    "AND t.status='ready' AND t.session_id IS NULL AND o.status='fulfilled' AND r.status='confirmed' "
    "AND p.source_type='portal_order' AND p.source_id=o.id AND p.kind='receipt' AND p.amount=t.amount "
    "AND t.slot_id=NEW.parking_slot_id AND t.customer_id=v.customer_id AND t.vehicle_type_id=v.vehicle_type_id "
    "AND NEW.check_in_time>=t.start_at AND NEW.check_in_time<t.arrival_deadline "
    f"AND t.start_at=NEW.prepaid_start_at AND t.end_at=NEW.prepaid_end_at AND {_session_match}))) "
    "OR (COALESCE(NEW.billing_policy_version,'')!='prepaid-window-v1' AND (NEW.timed_pass_id IS NOT NULL OR NEW.prepaid_start_at IS NOT NULL OR NEW.prepaid_end_at IS NOT NULL))",
    "session prepaid source invalid")
_admission_bound = ("COALESCE((SELECT MAX(bound.end_at) FROM ("
    "SELECT r.end_at FROM parking_reservations r JOIN vehicles v ON v.id=r.vehicle_id "
    "WHERE r.slot_id=NEW.parking_slot_id AND r.vehicle_id=NEW.vehicle_id AND r.customer_id=v.customer_id "
    "AND r.status='confirmed' AND r.start_at<=NEW.check_in_time AND r.arrival_deadline>NEW.check_in_time "
    "UNION ALL SELECT a.end_at FROM guaranteed_allocations a JOIN vehicles v ON v.id=a.vehicle_id "
    "WHERE a.slot_id=NEW.parking_slot_id AND a.vehicle_id=NEW.vehicle_id AND a.customer_id=v.customer_id "
    "AND a.status='active' AND a.start_at<=NEW.check_in_time AND a.end_at>NEW.check_in_time) bound), '9999-12-31')")
guard("trg_session_capacity_hold", "parking_sessions", "INSERT", "NEW.status='active' AND EXISTS ("
    f"SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id=NEW.parking_slot_id AND {_live} "
    f"AND h.start_at < {_admission_bound})", "slot has a live payment hold")
guard("trg_payment_prepaid_source", "payments", "INSERT", "NEW.source_type='portal_order' AND NEW.kind='receipt' AND NOT EXISTS ("
    "SELECT 1 FROM portal_orders o JOIN timed_parking_passes t ON t.order_id=o.id WHERE o.id=NEW.source_id "
    "AND o.amount=NEW.amount AND o.site_id=NEW.site_id AND o.product_kind IN ('hourly','daily') "
    "AND ((o.payment_mode='demo' AND NEW.method='demo') OR (o.payment_mode='manual' AND NEW.method IN ('cash','transfer')) "
    "OR (o.payment_mode='payos' AND NEW.method='transfer' AND NEW.collected_by_id IS NULL)))",
    "prepaid payment source or scope invalid")
for table, slots in (("parking_slots", "SELECT OLD.id"), ("zones", "SELECT id FROM parking_slots WHERE zone_id=OLD.id"),
                     ("vehicle_types", "SELECT id FROM parking_slots WHERE vehicle_type_id=OLD.id"),
                     ("parking_sites", "SELECT s.id FROM parking_slots s JOIN zones z ON z.id=s.zone_id WHERE z.site_id=OLD.id")):
    change = "NEW.is_active=0 AND OLD.is_active=1"
    if table == "parking_slots":
        change += " OR NEW.zone_id IS NOT OLD.zone_id OR NEW.vehicle_type_id IS NOT OLD.vehicle_type_id"
    elif table == "zones":
        change += " OR NEW.site_id IS NOT OLD.site_id"
    guard(f"trg_{table}_hold_operational", table, "UPDATE", f"({change}) AND EXISTS (SELECT 1 FROM parking_capacity_holds h WHERE h.slot_id IN ({slots}) AND {_live})",
        "cannot disable inventory with payment holds")

from expansion.site_models import LIVE_RESERVATION_SQL

PRE_COMPLETED_HOLD_GUARDS = {}
for name, sql in list(TIMED_SQLITE_GUARDS.items()):
    if "r.status IN ('confirmed','arrived')" in sql:
        PRE_COMPLETED_HOLD_GUARDS[name] = sql
        TIMED_SQLITE_GUARDS[name] = sql.replace("r.status IN ('confirmed','arrived')", LIVE_RESERVATION_SQL)
_postgres = [sql.replace("r.status IN ('confirmed','arrived')", LIVE_RESERVATION_SQL) for sql in _postgres]

for sql in TIMED_SQLITE_GUARDS.values():
    event.listen(Base.metadata, "after_create", DDL(sql.replace("%", "%%")).execute_if(dialect="sqlite"))
TIMED_POSTGRES_GUARD_SQL = "\n".join(_postgres)
event.listen(Base.metadata, "after_create", DDL(TIMED_POSTGRES_GUARD_SQL.replace("%", "%%")).execute_if(dialect="postgresql"))
