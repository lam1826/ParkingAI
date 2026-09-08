"""Nullable site attribution and request correlation, without rewriting ledger rows."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_02"
down_revision = "20260908_01"
branch_labels = None
depends_on = None


# Frozen with this migration; future runtime guards must not rewrite history.
SITE_FINANCE_POSTGRES_SQL = """
CREATE OR REPLACE FUNCTION parking_cash_shift_site_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.site_id IS DISTINCT FROM OLD.site_id THEN RAISE EXCEPTION 'cash shift site is immutable' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_cash_shift_site_immutable BEFORE UPDATE OF site_id ON cash_shifts FOR EACH ROW EXECUTE FUNCTION parking_cash_shift_site_guard();
CREATE OR REPLACE FUNCTION parking_payment_site_guard() RETURNS trigger AS $$
DECLARE expected_site integer; shift_site integer;
BEGIN
    IF NEW.kind='refund' THEN
        SELECT site_id INTO expected_site FROM payments WHERE id=NEW.original_payment_id;
        IF NEW.site_id IS DISTINCT FROM expected_site THEN RAISE EXCEPTION 'payment site mismatch' USING ERRCODE='23514'; END IF;
    ELSIF NEW.site_id IS NOT NULL THEN
        IF NEW.source_type='monthly_pass' THEN
            SELECT o.site_id INTO expected_site FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE p.id::text=NEW.source_id;
        ELSE
            SELECT z.site_id INTO expected_site FROM parking_sessions p JOIN parking_slots s ON s.id=p.parking_slot_id JOIN zones z ON z.id=s.zone_id WHERE p.id=NEW.source_id;
        END IF;
        IF NEW.site_id IS DISTINCT FROM expected_site THEN RAISE EXCEPTION 'payment site mismatch' USING ERRCODE='23514'; END IF;
    END IF;
    IF NEW.shift_id IS NOT NULL THEN
        SELECT site_id INTO shift_site FROM cash_shifts WHERE id=NEW.shift_id;
        IF shift_site IS NOT NULL AND shift_site IS DISTINCT FROM NEW.site_id THEN RAISE EXCEPTION 'payment shift site mismatch' USING ERRCODE='23514'; END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_payment_site_guard BEFORE INSERT ON payments FOR EACH ROW EXECUTE FUNCTION parking_payment_site_guard();
"""

def upgrade():
    for table, foreign_key, index in (
        ("cash_shifts", "fk_cash_shifts_site_id", "ix_cash_shifts_site_id"),
        ("payments", "fk_payments_site_id", "ix_payments_site_id"),
    ):
        op.add_column(table, sa.Column("site_id", sa.Integer(), nullable=True))
        op.create_foreign_key(foreign_key, table, "parking_sites", ["site_id"], ["id"])
        op.create_index(index, table, ["site_id"])
    op.add_column("audit_logs", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column("audit_logs", sa.Column("site_id", sa.Integer(), nullable=True))
    op.add_column("audit_logs", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_site_id", "audit_logs", ["site_id"])
    op.execute(SITE_FINANCE_POSTGRES_SQL)


def downgrade():
    # Attribution may already be part of published financial evidence.
    raise RuntimeError("Use a compatible application rollback; do not drop financial attribution automatically.")
