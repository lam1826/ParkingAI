"""Database backstops for nullable legacy and immutable admission tariffs."""
from core.money import MAX_EXACT_VND

SNAPSHOT_COLUMN_TYPES = {
    "billing_policy_version": "VARCHAR(32)", "rate_config_id": "INTEGER",
    "rate_ticket_type": "VARCHAR(8)", "rate_unit_price": "INTEGER",
    "rate_effective_date": "DATE",
}
_all_null = " AND ".join(f"NEW.{field} IS NULL" for field in SNAPSHOT_COLUMN_TYPES)
_all_present = " AND ".join(f"NEW.{field} IS NOT NULL" for field in SNAPSHOT_COLUMN_TYPES)
_changed = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in SNAPSHOT_COLUMN_TYPES)
_valid = (
    f"({_all_present}) AND NEW.billing_policy_version IN ('entry-v1','prepaid-window-v1') "
    "AND typeof(NEW.rate_config_id) = 'integer' AND NEW.rate_config_id > 0 "
    "AND NEW.rate_ticket_type IN ('HOURLY', 'DAILY') "
    "AND typeof(NEW.rate_unit_price) = 'integer' "
    f"AND NEW.rate_unit_price BETWEEN 0 AND {MAX_EXACT_VND} "
    "AND typeof(NEW.rate_effective_date) = 'text' "
    "AND NEW.rate_effective_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "AND substr(NEW.rate_effective_date, 1, 4) != '0000' "
    "AND date(NEW.rate_effective_date, '+0 days') = NEW.rate_effective_date "
    "AND NEW.rate_effective_date <= date(NEW.check_in_time) "
    "AND (NEW.monthly_pass_id IS NULL OR NEW.monthly_coverage_end IS NOT NULL)"
)
SQLITE_SNAPSHOT_INVALID = f"NOT ({_all_null}) AND NOT COALESCE(({_valid}), 0)"


def validate_sqlite_billing_snapshots(connection):
    invalid = connection.exec_driver_sql(
        "SELECT id FROM parking_sessions WHERE " + SQLITE_SNAPSHOT_INVALID.replace("NEW.", "") + " LIMIT 1"
    ).first()
    if invalid:
        raise RuntimeError(f"Bất biến billing snapshot không hợp lệ: {invalid[0]}")


BILLING_SQLITE_GUARDS = {
    "trg_parking_sessions_billing_snapshot_insert": (
        "CREATE TRIGGER IF NOT EXISTS trg_parking_sessions_billing_snapshot_insert "
        "BEFORE INSERT ON parking_sessions FOR EACH ROW "
        f"WHEN {SQLITE_SNAPSHOT_INVALID} "
        "BEGIN SELECT RAISE(ABORT, 'billing snapshot invalid'); END"
    ),
    "trg_parking_sessions_billing_snapshot_immutable": (
        "CREATE TRIGGER IF NOT EXISTS trg_parking_sessions_billing_snapshot_immutable "
        "BEFORE UPDATE ON parking_sessions FOR EACH ROW "
        f"WHEN {_changed} "
        "BEGIN SELECT RAISE(ABORT, 'billing snapshot immutable'); END"
    ),
    "trg_parking_sessions_billing_snapshot_replace": (
        "CREATE TRIGGER IF NOT EXISTS trg_parking_sessions_billing_snapshot_replace "
        "BEFORE INSERT ON parking_sessions FOR EACH ROW "
        "WHEN EXISTS (SELECT 1 FROM parking_sessions WHERE id = NEW.id "
        "AND (billing_policy_version IS NOT NULL OR NEW.billing_policy_version IS NOT NULL)) "
        "BEGIN SELECT RAISE(ABORT, 'billing snapshot immutable'); END"
    ),
    "trg_parking_sessions_billing_snapshot_delete": (
        "CREATE TRIGGER IF NOT EXISTS trg_parking_sessions_billing_snapshot_delete "
        "BEFORE DELETE ON parking_sessions FOR EACH ROW WHEN OLD.billing_policy_version IS NOT NULL "
        "BEGIN SELECT RAISE(ABORT, 'billing snapshot history cannot be deleted'); END"
    ),
    "trg_parking_sessions_cancelled_terminal": (
        "CREATE TRIGGER IF NOT EXISTS trg_parking_sessions_cancelled_terminal "
        "BEFORE UPDATE ON parking_sessions FOR EACH ROW "
        "WHEN OLD.status = 'cancelled' AND (NEW.status IS NOT OLD.status "
        "OR NEW.check_out_time IS NOT OLD.check_out_time OR NEW.parking_fee IS NOT OLD.parking_fee "
        "OR NEW.staff_out_id IS NOT OLD.staff_out_id) "
        "BEGIN SELECT RAISE(ABORT, 'cancelled parking session is terminal'); END"
    ),
}

BILLING_POSTGRES_GUARD_SQL = f"""
CREATE OR REPLACE FUNCTION parking_billing_snapshot_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.billing_policy_version IS NOT NULL THEN
            RAISE EXCEPTION 'billing snapshot history cannot be deleted' USING ERRCODE = '23514';
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.billing_policy_version, NEW.rate_config_id, NEW.rate_ticket_type,
               NEW.rate_unit_price, NEW.rate_effective_date) IS DISTINCT FROM
           ROW(OLD.billing_policy_version, OLD.rate_config_id, OLD.rate_ticket_type,
               OLD.rate_unit_price, OLD.rate_effective_date) THEN
            RAISE EXCEPTION 'billing snapshot immutable' USING ERRCODE = '23514';
        END IF;
        IF OLD.status = 'cancelled' AND ROW(NEW.status, NEW.check_out_time, NEW.parking_fee, NEW.staff_out_id)
            IS DISTINCT FROM ROW(OLD.status, OLD.check_out_time, OLD.parking_fee, OLD.staff_out_id) THEN
            RAISE EXCEPTION 'cancelled parking session is terminal' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NOT (NEW.billing_policy_version IS NULL AND NEW.rate_config_id IS NULL
        AND NEW.rate_ticket_type IS NULL AND NEW.rate_unit_price IS NULL AND NEW.rate_effective_date IS NULL)
        AND NOT COALESCE((NEW.billing_policy_version IN ('entry-v1','prepaid-window-v1') AND NEW.rate_config_id > 0
        AND NEW.rate_ticket_type IN ('HOURLY', 'DAILY') AND NEW.rate_unit_price BETWEEN 0 AND {MAX_EXACT_VND}
        AND NEW.rate_effective_date <= NEW.check_in_time::date
        AND (NEW.monthly_pass_id IS NULL OR NEW.monthly_coverage_end IS NOT NULL)), false) THEN
        RAISE EXCEPTION 'billing snapshot invalid' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_parking_sessions_billing_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON parking_sessions
FOR EACH ROW EXECUTE FUNCTION parking_billing_snapshot_guard();
"""
