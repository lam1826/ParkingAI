"""Append-only receipts and refunds, recorded at business-local collection time."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DDL, DateTime, ForeignKey, Index, String, event, text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import MAX_EXACT_VND, VND_DATABASE_TYPE
from database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(f"amount >= 0 AND amount <= {MAX_EXACT_VND}", name="ck_payment_amount"),
        CheckConstraint("source_type IN ('parking_session', 'monthly_pass')", name="ck_payment_source"),
        CheckConstraint("kind IN ('receipt', 'refund')", name="ck_payment_kind"),
        CheckConstraint("method IN ('cash', 'transfer', 'legacy_unknown', 'demo')", name="ck_payment_method"),
        CheckConstraint("method != 'demo' OR shift_id IS NULL", name="ck_payment_demo_unassigned"),
        CheckConstraint("method != 'legacy_unknown' OR shift_id IS NULL", name="ck_payment_legacy_unassigned"),
        CheckConstraint("(kind = 'receipt' AND original_payment_id IS NULL) OR (kind = 'refund' AND original_payment_id IS NOT NULL AND amount > 0 AND reason IS NOT NULL AND trim(reason) != '')", name="ck_payment_refund_reference"),
        Index("uq_payment_source_receipt", "source_type", "source_id", unique=True,
              sqlite_where=text("kind = 'receipt'"), postgresql_where=text("kind = 'receipt'")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(8))
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    method: Mapped[str] = mapped_column(String(16), default="cash")
    collected_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("cash_shifts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    original_payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), index=True)
    reason: Mapped[str | None] = mapped_column(String(500))


PAYMENT_SQLITE_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS trg_payment_immutable_update BEFORE UPDATE ON payments BEGIN SELECT RAISE(ABORT, 'payment is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_payment_immutable_delete BEFORE DELETE ON payments BEGIN SELECT RAISE(ABORT, 'payment is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_payment_integer BEFORE INSERT ON payments WHEN typeof(NEW.amount) != 'integer' BEGIN SELECT RAISE(ABORT, 'payment amount must be integer'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_payment_open_shift BEFORE INSERT ON payments WHEN NEW.shift_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM cash_shifts WHERE id = NEW.shift_id AND status = 'open' AND staff_id = NEW.collected_by_id AND opened_at <= NEW.created_at) BEGIN SELECT RAISE(ABORT, 'payment requires own open shift'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_payment_refund_bound BEFORE INSERT ON payments WHEN NEW.kind = 'refund' AND NOT EXISTS (SELECT 1 FROM payments original WHERE original.id = NEW.original_payment_id AND original.kind = 'receipt' AND original.source_type = NEW.source_type AND original.source_id = NEW.source_id AND original.created_at <= NEW.created_at AND original.amount >= NEW.amount + COALESCE((SELECT SUM(amount) FROM payments WHERE original_payment_id = NEW.original_payment_id AND kind = 'refund'), 0)) BEGIN SELECT RAISE(ABORT, 'refund exceeds original payment'); END",
)

# Polymorphic sources cannot use one SQL foreign key. Preserve the same
# referential/amount guarantees with source guards after all tables exist.
PAYMENT_SQLITE_SOURCE_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS trg_payment_receipt_source BEFORE INSERT ON payments WHEN NEW.kind = 'receipt' AND ((NEW.source_type = 'parking_session' AND NOT EXISTS (SELECT 1 FROM parking_sessions WHERE id = NEW.source_id AND status = 'completed' AND parking_fee = NEW.amount)) OR (NEW.source_type = 'monthly_pass' AND NOT EXISTS (SELECT 1 FROM monthly_passes WHERE CAST(id AS TEXT) = NEW.source_id AND price = NEW.amount))) BEGIN SELECT RAISE(ABORT, 'payment source or amount invalid'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_paid_parking_session_delete BEFORE DELETE ON parking_sessions WHEN EXISTS (SELECT 1 FROM payments WHERE source_type = 'parking_session' AND source_id = OLD.id) BEGIN SELECT RAISE(ABORT, 'paid parking session cannot be deleted'); END",
)

PAYMENT_POSTGRES_GUARD_SQL = """
CREATE OR REPLACE FUNCTION parking_payment_guard() RETURNS trigger AS $$
DECLARE original payments%%ROWTYPE; active_shift cash_shifts%%ROWTYPE; refunded numeric; source_amount bigint;
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

PAYMENT_POSTGRES_SOURCE_DELETE_SQL = """
CREATE OR REPLACE FUNCTION parking_paid_session_delete_guard() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM payments WHERE source_type = 'parking_session' AND source_id = OLD.id) THEN
        RAISE EXCEPTION 'paid parking session cannot be deleted' USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_paid_parking_session_delete BEFORE DELETE ON parking_sessions FOR EACH ROW EXECUTE FUNCTION parking_paid_session_delete_guard();
"""

for sql in PAYMENT_SQLITE_TRIGGERS:
    event.listen(Payment.__table__, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(Payment.__table__, "after_create", DDL(PAYMENT_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
for sql in PAYMENT_SQLITE_SOURCE_TRIGGERS:
    event.listen(Base.metadata, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(PAYMENT_POSTGRES_SOURCE_DELETE_SQL).execute_if(dialect="postgresql"))
