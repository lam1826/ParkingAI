"""Add reusable parking cards, immutable receipts and cash-shift accounting.

Revision ID: 20260906_01
Revises: 20260828_01

Legacy monthly collection times are approximated from UTC creation metadata;
payment method and collector stay unknown. Every backfill is source-idempotent.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260906_01"
down_revision = "20260828_01"
branch_labels = None
depends_on = None

MAX_VND = 9_007_199_254_740_991
SOURCE_DELETE_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_paid_session_delete_guard() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM payments WHERE source_type = 'parking_session' AND source_id = OLD.id) THEN
        RAISE EXCEPTION 'paid parking session cannot be deleted' USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_paid_parking_session_delete BEFORE DELETE ON parking_sessions FOR EACH ROW EXECUTE FUNCTION parking_paid_session_delete_guard();
"""
PAYMENT_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_payment_guard() RETURNS trigger AS $$
DECLARE original payments%ROWTYPE; active_shift cash_shifts%ROWTYPE; refunded numeric; source_amount bigint;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'payment is immutable' USING ERRCODE = '23514'; END IF;
    IF NEW.kind = 'receipt' THEN
        IF NEW.source_type = 'parking_session' THEN
            SELECT parking_fee INTO source_amount FROM parking_sessions WHERE id = NEW.source_id AND status = 'completed' FOR UPDATE;
        ELSE
            SELECT price INTO source_amount FROM monthly_passes WHERE id::text = NEW.source_id FOR UPDATE;
        END IF;
        IF NOT FOUND OR source_amount IS DISTINCT FROM NEW.amount THEN RAISE EXCEPTION 'payment source or amount invalid' USING ERRCODE = '23514'; END IF;
    END IF;
    IF NEW.kind = 'refund' THEN
        SELECT * INTO original FROM payments WHERE id = NEW.original_payment_id FOR UPDATE;
        IF NOT FOUND OR original.kind <> 'receipt' OR original.source_type <> NEW.source_type OR original.source_id <> NEW.source_id OR NEW.created_at < original.created_at THEN
            RAISE EXCEPTION 'refund original payment invalid' USING ERRCODE = '23514';
        END IF;
        SELECT COALESCE(SUM(amount), 0) INTO refunded FROM payments WHERE original_payment_id = NEW.original_payment_id AND kind = 'refund';
        IF NEW.amount + refunded > original.amount THEN RAISE EXCEPTION 'refund exceeds original payment' USING ERRCODE = '23514'; END IF;
    END IF;
    IF NEW.shift_id IS NOT NULL THEN
        SELECT * INTO active_shift FROM cash_shifts WHERE id = NEW.shift_id FOR UPDATE;
        IF NOT FOUND OR active_shift.status <> 'open' OR active_shift.staff_id IS DISTINCT FROM NEW.collected_by_id OR NEW.created_at < active_shift.opened_at THEN
            RAISE EXCEPTION 'payment requires own open shift' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_payment_guard BEFORE INSERT OR UPDATE OR DELETE ON payments FOR EACH ROW EXECUTE FUNCTION parking_payment_guard();
"""
SHIFT_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_cash_shift_guard() RETURNS trigger AS $$
DECLARE cash_total numeric;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'open' THEN RAISE EXCEPTION 'cash shift must start open' USING ERRCODE = '23514'; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'cash shift is immutable' USING ERRCODE = '23514'; END IF;
    IF OLD.status = 'closed' OR NEW.id IS DISTINCT FROM OLD.id OR NEW.staff_id IS DISTINCT FROM OLD.staff_id OR NEW.opened_at IS DISTINCT FROM OLD.opened_at OR NEW.opening_cash IS DISTINCT FROM OLD.opening_cash THEN
        RAISE EXCEPTION 'cash shift is immutable' USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'closed' THEN
        SELECT COALESCE(SUM(CASE WHEN kind = 'receipt' THEN amount ELSE -amount END), 0) INTO cash_total FROM payments WHERE shift_id = NEW.id AND method = 'cash';
        IF NEW.expected_cash <> NEW.opening_cash + cash_total OR EXISTS (SELECT 1 FROM payments WHERE shift_id = NEW.id AND created_at > NEW.closed_at) THEN
            RAISE EXCEPTION 'cash shift close balance invalid' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_cash_shift_guard BEFORE INSERT OR UPDATE OR DELETE ON cash_shifts FOR EACH ROW EXECUTE FUNCTION parking_cash_shift_guard();
"""


def upgrade():
    # NULL is intentional for historical admissions: do not grant extensions
    # retroactively from renewals bought after the original check-in.
    op.add_column("parking_sessions", sa.Column("monthly_coverage_end", sa.Date()))
    op.create_check_constraint(
        "ck_parking_sessions_monthly_coverage", "parking_sessions",
        "monthly_coverage_end IS NULL OR (monthly_pass_id IS NOT NULL AND monthly_coverage_end BETWEEN DATE '0001-01-01' AND DATE '9999-12-31' AND monthly_coverage_end >= check_in_time::date)",
    )
    op.create_table(
        "parking_cards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("vehicle_id", sa.Integer, sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.add_column("monthly_passes", sa.Column("card_id", sa.Integer, sa.ForeignKey("parking_cards.id", name="fk_monthly_passes_card")))
    op.add_column("monthly_passes", sa.Column("renewal_key", sa.String(64)))
    op.create_index("uq_monthly_passes_renewal_key", "monthly_passes", ["renewal_key"], unique=True)
    op.create_table(
        "cash_shifts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("staff_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opened_at", sa.DateTime, nullable=False),
        sa.Column("closed_at", sa.DateTime),
        sa.Column("opening_cash", sa.BigInteger, nullable=False),
        sa.Column("counted_cash", sa.BigInteger),
        sa.Column("expected_cash", sa.BigInteger),
        sa.Column("difference", sa.BigInteger),
        sa.Column("status", sa.String(8), nullable=False),
        sa.CheckConstraint(f"opening_cash BETWEEN 0 AND {MAX_VND}", name="ck_shift_opening_cash"),
        sa.CheckConstraint(f"counted_cash IS NULL OR counted_cash BETWEEN 0 AND {MAX_VND}", name="ck_shift_counted_cash"),
        sa.CheckConstraint(f"expected_cash IS NULL OR expected_cash BETWEEN -{MAX_VND} AND {MAX_VND}", name="ck_shift_expected_cash"),
        sa.CheckConstraint(f"difference IS NULL OR difference BETWEEN -{MAX_VND} AND {MAX_VND}", name="ck_shift_difference"),
        sa.CheckConstraint("(status = 'open' AND closed_at IS NULL AND counted_cash IS NULL AND expected_cash IS NULL AND difference IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL AND closed_at >= opened_at AND counted_cash IS NOT NULL AND expected_cash IS NOT NULL AND difference IS NOT NULL AND difference = counted_cash - expected_cash)", name="ck_shift_state"),
    )
    op.create_index("ix_cash_shifts_staff_id", "cash_shifts", ["staff_id"])
    op.create_index("uq_cash_shift_one_open_per_staff", "cash_shifts", ["staff_id"], unique=True, postgresql_where=sa.text("status = 'open'"))
    op.create_table(
        "payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("collected_by_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("original_payment_id", sa.String(36), sa.ForeignKey("payments.id")),
        sa.Column("reason", sa.String(500)),
        sa.CheckConstraint(f"amount >= 0 AND amount <= {MAX_VND}", name="ck_payment_amount"),
        sa.CheckConstraint("source_type IN ('parking_session', 'monthly_pass')", name="ck_payment_source"),
        sa.CheckConstraint("kind IN ('receipt', 'refund')", name="ck_payment_kind"),
        sa.CheckConstraint("method IN ('cash', 'transfer', 'legacy_unknown')", name="ck_payment_method"),
        sa.CheckConstraint("method != 'legacy_unknown' OR shift_id IS NULL", name="ck_payment_legacy_unassigned"),
        sa.CheckConstraint("(kind = 'receipt' AND original_payment_id IS NULL) OR (kind = 'refund' AND original_payment_id IS NOT NULL AND amount > 0 AND reason IS NOT NULL AND trim(reason) != '')", name="ck_payment_refund_reference"),
    )
    for column in ("collected_by_id", "shift_id", "created_at", "original_payment_id"):
        op.create_index("ix_payments_" + column, "payments", [column])
    op.create_index("uq_payment_source_receipt", "payments", ["source_type", "source_id"], unique=True, postgresql_where=sa.text("kind = 'receipt'"))

    op.execute("""
        INSERT INTO parking_cards (code, customer_id, vehicle_id, created_at)
        SELECT pass_code, customer_id, vehicle_id, created_at FROM monthly_passes
        WHERE pass_code IS NOT NULL ON CONFLICT (code) DO NOTHING;
        UPDATE monthly_passes period SET card_id = card.id FROM parking_cards card
        WHERE period.card_id IS NULL AND card.code = period.pass_code
          AND card.customer_id = period.customer_id AND card.vehicle_id = period.vehicle_id;
        INSERT INTO payments (id, source_type, source_id, kind, amount, method, created_at, idempotency_key, reason)
        SELECT md5('receipt:parking_session:' || id), 'parking_session', id, 'receipt', parking_fee,
               'legacy_unknown', check_out_time, 'receipt:parking_session:' || id,
               'Legacy import; payment method and collector were not recorded.'
        FROM parking_sessions WHERE status = 'completed' AND parking_fee IS NOT NULL
        ON CONFLICT DO NOTHING;
        INSERT INTO payments (id, source_type, source_id, kind, amount, method, created_at, idempotency_key, reason)
        SELECT md5('receipt:monthly_pass:' || id::text), 'monthly_pass', id::text, 'receipt', price,
               'legacy_unknown', (created_at AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Ho_Chi_Minh',
               'receipt:monthly_pass:' || id::text,
               'Legacy import; monthly collection time approximated from UTC creation metadata; method and collector unknown.'
        FROM monthly_passes ON CONFLICT DO NOTHING;
    """)
    op.execute(PAYMENT_GUARD_SQL)
    op.execute(SHIFT_GUARD_SQL)
    op.execute(SOURCE_DELETE_GUARD_SQL)
    op.execute("""
        CREATE OR REPLACE FUNCTION parking_monthly_coverage_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                IF NEW.monthly_coverage_end IS DISTINCT FROM OLD.monthly_coverage_end THEN
                    RAISE EXCEPTION 'monthly coverage snapshot immutable' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF NEW.monthly_coverage_end IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM monthly_passes WHERE id = NEW.monthly_pass_id AND end_date <= NEW.monthly_coverage_end
            ) THEN
                RAISE EXCEPTION 'monthly coverage snapshot invalid' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_monthly_coverage_guard BEFORE INSERT OR UPDATE ON parking_sessions
        FOR EACH ROW EXECUTE FUNCTION parking_monthly_coverage_guard();
        CREATE OR REPLACE FUNCTION parking_monthly_finance_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM payments WHERE source_type = 'monthly_pass' AND source_id = OLD.id::text AND kind = 'receipt') THEN
                    RAISE EXCEPTION 'paid monthly period is immutable' USING ERRCODE = '23514';
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF ((OLD.card_id IS NOT NULL AND NEW.card_id IS DISTINCT FROM OLD.card_id) OR
                    (EXISTS (SELECT 1 FROM payments WHERE source_type = 'monthly_pass' AND source_id = OLD.id::text AND kind = 'receipt') AND
                     ROW(NEW.customer_id, NEW.vehicle_id, NEW.pass_code, NEW.price, NEW.start_date, NEW.end_date) IS DISTINCT FROM
                     ROW(OLD.customer_id, OLD.vehicle_id, OLD.pass_code, OLD.price, OLD.start_date, OLD.end_date))) THEN
                    RAISE EXCEPTION 'paid monthly period is immutable' USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NEW.card_id IS NOT NULL THEN PERFORM id FROM parking_cards WHERE id = NEW.card_id FOR UPDATE; END IF;
            IF NEW.card_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM parking_cards WHERE id = NEW.card_id AND customer_id = NEW.customer_id AND vehicle_id = NEW.vehicle_id) THEN
                RAISE EXCEPTION 'monthly card binding mismatch' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_monthly_finance_guard BEFORE INSERT OR UPDATE OR DELETE ON monthly_passes
        FOR EACH ROW EXECUTE FUNCTION parking_monthly_finance_guard();
        CREATE OR REPLACE FUNCTION parking_card_identity_guard() RETURNS trigger AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM monthly_passes WHERE card_id = OLD.id) AND
               ROW(NEW.id, NEW.code, NEW.customer_id, NEW.vehicle_id) IS DISTINCT FROM ROW(OLD.id, OLD.code, OLD.customer_id, OLD.vehicle_id) THEN
                RAISE EXCEPTION 'parking card identity is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_parking_card_identity_guard BEFORE UPDATE ON parking_cards
        FOR EACH ROW EXECUTE FUNCTION parking_card_identity_guard();
    """)


def downgrade():
    raise RuntimeError("Financial history cannot be dropped automatically; restore a verified pre-migration backup.")
