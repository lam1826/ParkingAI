"""Freeze admission tariffs without rewriting legacy bills or active stays.

Downgrade keeps the additive audit history. Billing SQL is frozen here instead
of importing changing application modules into an applied migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260915_01"
down_revision = "20260908_03"
branch_labels = None
depends_on = None

BILLING_POSTGRES_GUARD_SQL = """
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
        AND NOT COALESCE((NEW.billing_policy_version = 'entry-v1' AND NEW.rate_config_id > 0
        AND NEW.rate_ticket_type IN ('HOURLY', 'DAILY') AND NEW.rate_unit_price BETWEEN 0 AND 9007199254740991
        AND NEW.rate_effective_date <= NEW.check_in_time::date
        AND (NEW.monthly_pass_id IS NULL OR NEW.monthly_coverage_end IS NOT NULL)), false) THEN
        RAISE EXCEPTION 'billing snapshot invalid' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_parking_sessions_billing_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON parking_sessions
FOR EACH ROW EXECUTE FUNCTION parking_billing_snapshot_guard();
"""

SESSION_GUARD_SQL = """
        CREATE OR REPLACE FUNCTION parkingai_validate_session()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            session_vehicle_type integer;
            session_zone integer;
        BEGIN
            -- One lock order for every admission path: vehicle -> type ->
            -- slot -> zone. Price updates share the type lock; slot/zone
            -- updates share their row locks. This closes cross-container
            -- check-then-act races under READ COMMITTED.
            SELECT vehicle_type_id INTO session_vehicle_type
            FROM vehicles WHERE id = NEW.vehicle_id FOR UPDATE;
            PERFORM 1 FROM vehicle_types
            WHERE id = session_vehicle_type FOR SHARE;
            IF NEW.parking_slot_id IS NOT NULL THEN
                SELECT zone_id INTO session_zone FROM parking_slots
                WHERE id = NEW.parking_slot_id FOR UPDATE;
                PERFORM 1 FROM zones WHERE id = session_zone FOR UPDATE;
            END IF;

            IF TG_OP = 'UPDATE' THEN
                IF NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id
                   OR NEW.parking_slot_id IS DISTINCT FROM OLD.parking_slot_id
                   OR NEW.monthly_pass_id IS DISTINCT FROM OLD.monthly_pass_id
                   OR NEW.check_in_time IS DISTINCT FROM OLD.check_in_time
                   OR NEW.staff_in_id IS DISTINCT FROM OLD.staff_in_id THEN
                    RAISE EXCEPTION 'parking session identity is immutable';
                END IF;

                IF OLD.status = 'completed' AND (
                    NEW.status IS DISTINCT FROM OLD.status
                    OR NEW.check_out_time IS DISTINCT FROM OLD.check_out_time
                    OR NEW.parking_fee IS DISTINCT FROM OLD.parking_fee
                    OR NEW.staff_out_id IS DISTINCT FROM OLD.staff_out_id
                ) THEN
                    RAISE EXCEPTION 'completed parking session is immutable';
                END IF;

                IF NEW.status = 'checking_out' AND OLD.status <> 'active' THEN
                    RAISE EXCEPTION 'parking session status invalid';
                END IF;
                IF OLD.status = 'checking_out' AND NEW.status <> 'completed' THEN
                    RAISE EXCEPTION 'parking session status invalid';
                END IF;
            ELSIF NEW.status = 'checking_out' THEN
                RAISE EXCEPTION 'parking session status invalid';
            END IF;

            -- Entitlement is a check-in snapshot. Deactivating a pass later
            -- must not prevent the already-admitted session from completing.
            IF TG_OP = 'INSERT' AND NEW.monthly_pass_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM monthly_passes mp
                WHERE mp.id = NEW.monthly_pass_id
                  AND mp.vehicle_id = NEW.vehicle_id
                  AND mp.is_active
                  AND mp.start_date <= NEW.check_in_time::date
                  AND mp.end_date >= NEW.check_in_time::date
            ) THEN
                RAISE EXCEPTION 'monthly pass is not eligible at check-in';
            END IF;

            IF NEW.status = 'active' AND NEW.billing_policy_version IS NULL AND NOT EXISTS (
                SELECT 1 FROM price_configs pc
                WHERE pc.vehicle_type_id = session_vehicle_type AND pc.is_active
                  AND pc.effective_date <= NEW.check_in_time::date
            ) THEN
                RAISE EXCEPTION 'active parking session requires effective price config';
            END IF;

            IF NEW.status = 'active' AND NEW.parking_slot_id IS NOT NULL
               AND NOT EXISTS (
                SELECT 1 FROM parking_slots ps
                JOIN zones z ON z.id = ps.zone_id
                JOIN vehicles v ON v.id = NEW.vehicle_id
                WHERE ps.id = NEW.parking_slot_id
                  AND ps.vehicle_type_id = v.vehicle_type_id
                  AND ps.is_active AND z.is_active
            ) THEN
                RAISE EXCEPTION 'parking slot is not eligible for active session';
            END IF;
            RETURN NEW;
        END;
        $$;
"""

PRICE_GUARD_SQL = """
        CREATE OR REPLACE FUNCTION parkingai_guard_price_with_active_sessions()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            protected_type integer := OLD.vehicle_type_id;
        BEGIN
            -- Serialize with session admission for this vehicle type. Without
            -- the shared lock, two READ COMMITTED statements could both pass
            -- their pre-check and commit an active stay without a rate.
            PERFORM 1 FROM vehicle_types
            WHERE id = protected_type FOR UPDATE;
            IF OLD.is_active AND EXISTS (
                SELECT 1 FROM parking_sessions ps
                JOIN vehicles v ON v.id = ps.vehicle_id
                WHERE ps.status IN ('active', 'checking_out') AND ps.billing_policy_version IS NULL
                  AND v.vehicle_type_id = protected_type
            ) THEN
                IF TG_OP = 'DELETE' OR NEW.vehicle_type_id IS DISTINCT FROM OLD.vehicle_type_id
                   OR NEW.ticket_type IS DISTINCT FROM OLD.ticket_type
                   OR NEW.price IS DISTINCT FROM OLD.price
                   OR NEW.effective_date IS DISTINCT FROM OLD.effective_date
                   OR NEW.is_active IS DISTINCT FROM OLD.is_active THEN
                    RAISE EXCEPTION 'active parking session uses price config';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END;
        $$;
"""


def upgrade():
    for name, column_type in (
        ("billing_policy_version", sa.String(32)), ("rate_config_id", sa.Integer()),
        ("rate_ticket_type", sa.String(8)), ("rate_unit_price", sa.BigInteger()),
        ("rate_effective_date", sa.Date()),
    ):
        op.add_column("parking_sessions", sa.Column(name, column_type, nullable=True))
    op.execute(BILLING_POSTGRES_GUARD_SQL)
    op.execute(SESSION_GUARD_SQL)
    op.execute(PRICE_GUARD_SQL)


def downgrade():
    raise RuntimeError("Retain billing history and use an entry-v1-compatible release or a forward fix; pre-snapshot applications cannot safely bill new stays.")
