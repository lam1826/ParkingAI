"""Attribute counter-sold monthly receipts to the selling site (review 05/10/2026, P1-1).

The previous ``parking_payment_site_guard`` only accepted a non-NULL site on a
``monthly_pass`` receipt when the period came from a portal order. Counter
sales and counter renewals have no order, so a seller with an open site-bound
cash shift got HTTP 409 and, without a shift, the receipt was stored with
``site_id`` NULL and never reached site finance, shift reconciliation or the
refund queues.

This revision only replaces the trigger function body: a counter period (no
portal order) may carry the seller's site; portal periods stay pinned to their
order's site, refunds to their receipt's site and shift-bound rows to the
shift's site. No ledger row is rewritten (payments are append-only by
``trg_payment_guard``); historical site-less receipts stay labelled as
historical rows with no known site.
"""
from alembic import op

revision = "20261005_12"
down_revision = "20261005_11"
branch_labels = None
depends_on = None

# Frozen definitions, independent of mutable application modules.
# SQLite twin of the guard (db_rollout recreates SQLite triggers from the guard
# module; these frozen texts let the upgrade bridge accept/replace exactly the
# previous definition). Verbatim copies; never edit.
PREVIOUS_SQLITE_GUARDS = {'trg_payment_site_guard': "CREATE TRIGGER IF NOT EXISTS trg_payment_site_guard BEFORE INSERT ON payments WHEN\n        (NEW.site_id IS NOT NULL AND NEW.kind = 'receipt' AND (\n            (NEW.source_type = 'session_credit' AND NEW.site_id IS NOT (SELECT q.site_id FROM session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id WHERE c.id=NEW.source_id)) OR\n            (NEW.source_type = 'monthly_pass' AND NEW.site_id IS NOT (SELECT o.site_id FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE CAST(p.id AS TEXT)=NEW.source_id)) OR\n            (NEW.source_type = 'parking_session' AND NEW.site_id IS NOT (SELECT z.site_id FROM parking_sessions p JOIN parking_slots s ON s.id=p.parking_slot_id JOIN zones z ON z.id=s.zone_id WHERE p.id=NEW.source_id))))\n        OR (NEW.kind = 'refund' AND NEW.site_id IS NOT (SELECT site_id FROM payments WHERE id=NEW.original_payment_id))\n        OR (NEW.shift_id IS NOT NULL AND EXISTS (SELECT 1 FROM cash_shifts c WHERE c.id=NEW.shift_id AND c.site_id IS NOT NULL AND c.site_id IS NOT NEW.site_id))\n        BEGIN SELECT RAISE(ABORT, 'payment site mismatch'); END"}
SQLITE_GUARDS = {'trg_payment_site_guard': "CREATE TRIGGER IF NOT EXISTS trg_payment_site_guard BEFORE INSERT ON payments WHEN\n        (NEW.site_id IS NOT NULL AND NEW.kind = 'receipt' AND (\n            (NEW.source_type = 'session_credit' AND NEW.site_id IS NOT (SELECT q.site_id FROM session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id WHERE c.id=NEW.source_id)) OR\n            (NEW.source_type = 'monthly_pass' AND EXISTS (SELECT 1 FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE CAST(p.id AS TEXT)=NEW.source_id) AND NEW.site_id IS NOT (SELECT o.site_id FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE CAST(p.id AS TEXT)=NEW.source_id)) OR\n            (NEW.source_type = 'parking_session' AND NEW.site_id IS NOT (SELECT z.site_id FROM parking_sessions p JOIN parking_slots s ON s.id=p.parking_slot_id JOIN zones z ON z.id=s.zone_id WHERE p.id=NEW.source_id))))\n        OR (NEW.kind = 'refund' AND NEW.site_id IS NOT (SELECT site_id FROM payments WHERE id=NEW.original_payment_id))\n        OR (NEW.shift_id IS NOT NULL AND EXISTS (SELECT 1 FROM cash_shifts c WHERE c.id=NEW.shift_id AND c.site_id IS NOT NULL AND c.site_id IS NOT NEW.site_id))\n        BEGIN SELECT RAISE(ABORT, 'payment site mismatch'); END"}

PREVIOUS_POSTGRES_SQL = """
CREATE OR REPLACE FUNCTION parking_payment_site_guard() RETURNS trigger AS $$
DECLARE expected_site integer; shift_site integer;
BEGIN
    IF NEW.kind='refund' THEN
        SELECT site_id INTO expected_site FROM payments WHERE id=NEW.original_payment_id;
        IF NEW.site_id IS DISTINCT FROM expected_site THEN RAISE EXCEPTION 'payment site mismatch' USING ERRCODE='23514'; END IF;
    ELSIF NEW.site_id IS NOT NULL THEN
        IF NEW.source_type='monthly_pass' THEN
            SELECT o.site_id INTO expected_site FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE p.id::text=NEW.source_id;
        ELSIF NEW.source_type='portal_order' THEN
            SELECT site_id INTO expected_site FROM portal_orders WHERE id=NEW.source_id;
        ELSIF NEW.source_type='session_credit' THEN
            SELECT q.site_id INTO expected_site FROM session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id WHERE c.id=NEW.source_id;
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
"""

UPGRADE_POSTGRES_SQL = """
CREATE OR REPLACE FUNCTION parking_payment_site_guard() RETURNS trigger AS $$
DECLARE expected_site integer; shift_site integer;
BEGIN
    IF NEW.kind='refund' THEN
        SELECT site_id INTO expected_site FROM payments WHERE id=NEW.original_payment_id;
        IF NEW.site_id IS DISTINCT FROM expected_site THEN RAISE EXCEPTION 'payment site mismatch' USING ERRCODE='23514'; END IF;
    ELSIF NEW.site_id IS NOT NULL THEN
        IF NEW.source_type='monthly_pass' THEN
            SELECT o.site_id INTO expected_site FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE p.id::text=NEW.source_id;
            -- A counter-sold period has no order owning its site: the seller's
            -- site (and the shift check below) attributes its receipt.
            IF NOT FOUND THEN expected_site := NEW.site_id; END IF;
        ELSIF NEW.source_type='portal_order' THEN
            SELECT site_id INTO expected_site FROM portal_orders WHERE id=NEW.source_id;
        ELSIF NEW.source_type='session_credit' THEN
            SELECT q.site_id INTO expected_site FROM session_fee_credits c JOIN session_fee_quotes q ON q.id=c.quote_id WHERE c.id=NEW.source_id;
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
"""


def upgrade():
    # The trigger itself (trg_payment_site_guard) keeps calling this function.
    op.execute(UPGRADE_POSTGRES_SQL)


def downgrade():
    # Receipts already attributed by the newer guard stay valid: the guard only
    # runs on INSERT, so restoring the stricter predecessor rewrites nothing.
    op.execute(PREVIOUS_POSTGRES_SQL)
