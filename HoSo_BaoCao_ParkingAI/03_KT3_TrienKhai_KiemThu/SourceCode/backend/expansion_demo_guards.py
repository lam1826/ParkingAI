"""Keep simulated payments outside real collections, including direct SQL writes."""
from sqlalchemy import DDL, event, text

from database import Base


DEMO_SQLITE_GUARD_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_payment_demo_boundary BEFORE INSERT ON payments
WHEN (NEW.method='demo' AND (NEW.source_type!='monthly_pass' OR NEW.shift_id IS NOT NULL
      OR (NEW.kind='receipt' AND NEW.collected_by_id IS NOT NULL)))
  OR (NEW.kind='refund' AND EXISTS (SELECT 1 FROM payments original
      WHERE original.id=NEW.original_payment_id AND ((original.method='demo') != (NEW.method='demo'))))
BEGIN SELECT RAISE(ABORT, 'demo payment cannot be mixed with real collection'); END
"""

DEMO_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_payment_demo_boundary() RETURNS trigger AS $$
BEGIN
    IF (NEW.method='demo' AND (NEW.source_type!='monthly_pass' OR NEW.shift_id IS NOT NULL
        OR (NEW.kind='receipt' AND NEW.collected_by_id IS NOT NULL)))
       OR (NEW.kind='refund' AND EXISTS (SELECT 1 FROM payments original
           WHERE original.id=NEW.original_payment_id AND ((original.method='demo') != (NEW.method='demo')))) THEN
        RAISE EXCEPTION 'demo payment cannot be mixed with real collection' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_payment_demo_boundary BEFORE INSERT ON payments
FOR EACH ROW EXECUTE FUNCTION parking_payment_demo_boundary();
"""


def validate_demo_ledger(connection) -> None:
    invalid = connection.execute(text("""
        SELECT payment.id FROM payments payment LEFT JOIN payments original ON original.id=payment.original_payment_id
        WHERE (payment.method='demo' AND (payment.source_type!='monthly_pass' OR payment.shift_id IS NOT NULL
               OR (payment.kind='receipt' AND payment.collected_by_id IS NOT NULL)))
           OR (payment.kind='refund' AND ((original.method='demo') != (payment.method='demo')))
        ORDER BY payment.id LIMIT 1
    """)).first()
    if invalid:
        raise RuntimeError(f"Bất biến tách thanh toán demo khỏi tiền thực không hợp lệ: {tuple(invalid)}")


event.listen(Base.metadata, "after_create", DDL(DEMO_SQLITE_GUARD_SQL).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(DEMO_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
