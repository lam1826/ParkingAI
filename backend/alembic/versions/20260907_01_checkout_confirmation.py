"""Store explicit checkout confirmation without inventing legacy history.

Revision ID: 20260907_01
Revises: 20260906_01

Both columns are nullable and have no default, so the preceding application
continues to operate during the rolling upgrade. Existing completed rows keep
a NULL pair. Application rollback retains this additive schema and history.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260907_01"
down_revision = "20260906_01"
branch_labels = None
depends_on = None

CHECKOUT_CONFIRMATION_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_checkout_confirmation_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.checkout_quote_hash IS NOT NULL OR NEW.checkout_payment_method IS NOT NULL THEN
            RAISE EXCEPTION 'checkout confirmation requires completion' USING ERRCODE = '23514';
        END IF;
    ELSIF ROW(NEW.checkout_quote_hash, NEW.checkout_payment_method) IS DISTINCT FROM
          ROW(OLD.checkout_quote_hash, OLD.checkout_payment_method) AND NOT (
              OLD.status IS NOT DISTINCT FROM 'checking_out' AND NEW.status IS NOT DISTINCT FROM 'completed'
              AND OLD.checkout_quote_hash IS NULL AND OLD.checkout_payment_method IS NULL) THEN
        RAISE EXCEPTION 'checkout confirmation invalid or immutable' USING ERRCODE = '23514';
    END IF;
    IF (NEW.checkout_quote_hash IS NULL AND NEW.checkout_payment_method IS NOT NULL) OR
       (NEW.checkout_quote_hash IS NOT NULL AND (
           length(NEW.checkout_quote_hash) != 64 OR NEW.checkout_quote_hash !~ '^[0-9a-f]{64}$'
           OR NEW.status IS DISTINCT FROM 'completed'
           OR NEW.staff_out_id IS NULL OR NEW.parking_fee IS NULL OR NEW.parking_fee < 0
           OR (NEW.parking_fee = 0 AND NEW.checkout_payment_method IS NOT NULL)
           OR (NEW.parking_fee > 0 AND COALESCE(NEW.checkout_payment_method, '') NOT IN ('cash', 'transfer')))) THEN
        RAISE EXCEPTION 'checkout confirmation invalid or immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_parking_sessions_checkout_confirmation_guard BEFORE INSERT OR UPDATE ON parking_sessions
FOR EACH ROW EXECUTE FUNCTION parking_checkout_confirmation_guard();
"""


def upgrade():
    op.add_column("parking_sessions", sa.Column("checkout_quote_hash", sa.String(64), nullable=True))
    op.add_column("parking_sessions", sa.Column("checkout_payment_method", sa.String(8), nullable=True))
    op.execute(CHECKOUT_CONFIRMATION_POSTGRES_GUARD_SQL)


def downgrade():
    raise RuntimeError(
        "Checkout confirmation history cannot be dropped automatically; "
        "roll back the application image while retaining the additive schema."
    )
