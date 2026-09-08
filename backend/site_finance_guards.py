"""Additive site attribution: never rewrite the historical financial ledger."""
from sqlalchemy import DDL, event
from database import Base

SITE_FINANCE_SQLITE_GUARDS = {
    "trg_cash_shift_site_immutable": "CREATE TRIGGER IF NOT EXISTS trg_cash_shift_site_immutable BEFORE UPDATE OF site_id ON cash_shifts WHEN NEW.site_id IS NOT OLD.site_id BEGIN SELECT RAISE(ABORT, 'cash shift site is immutable'); END",
    "trg_payment_site_guard": """CREATE TRIGGER IF NOT EXISTS trg_payment_site_guard BEFORE INSERT ON payments WHEN
        (NEW.site_id IS NOT NULL AND NEW.kind = 'receipt' AND (
            (NEW.source_type = 'monthly_pass' AND NEW.site_id IS NOT (SELECT o.site_id FROM monthly_passes p JOIN portal_orders o ON p.renewal_key='portal:' || o.id WHERE CAST(p.id AS TEXT)=NEW.source_id)) OR
            (NEW.source_type = 'parking_session' AND NEW.site_id IS NOT (SELECT z.site_id FROM parking_sessions p JOIN parking_slots s ON s.id=p.parking_slot_id JOIN zones z ON z.id=s.zone_id WHERE p.id=NEW.source_id))))
        OR (NEW.kind = 'refund' AND NEW.site_id IS NOT (SELECT site_id FROM payments WHERE id=NEW.original_payment_id))
        OR (NEW.shift_id IS NOT NULL AND EXISTS (SELECT 1 FROM cash_shifts c WHERE c.id=NEW.shift_id AND c.site_id IS NOT NULL AND c.site_id IS NOT NEW.site_id))
        BEGIN SELECT RAISE(ABORT, 'payment site mismatch'); END""",
}

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

for sql in SITE_FINANCE_SQLITE_GUARDS.values():
    event.listen(Base.metadata, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(SITE_FINANCE_POSTGRES_SQL).execute_if(dialect="postgresql"))
