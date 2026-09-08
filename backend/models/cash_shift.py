"""An operator's cash drawer with an immutable close count."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DDL, DateTime, ForeignKey, Index, String, event, text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import MAX_EXACT_VND, VND_DATABASE_TYPE
from database import Base


class CashShift(Base):
    __tablename__ = "cash_shifts"
    __table_args__ = (
        Index("uq_cash_shift_one_open_per_staff", "staff_id", unique=True,
              sqlite_where=text("status = 'open'"), postgresql_where=text("status = 'open'")),
        CheckConstraint(f"opening_cash BETWEEN 0 AND {MAX_EXACT_VND}", name="ck_shift_opening_cash"),
        CheckConstraint(f"counted_cash IS NULL OR counted_cash BETWEEN 0 AND {MAX_EXACT_VND}", name="ck_shift_counted_cash"),
        CheckConstraint(f"expected_cash IS NULL OR expected_cash BETWEEN -{MAX_EXACT_VND} AND {MAX_EXACT_VND}", name="ck_shift_expected_cash"),
        CheckConstraint(f"difference IS NULL OR difference BETWEEN -{MAX_EXACT_VND} AND {MAX_EXACT_VND}", name="ck_shift_difference"),
        CheckConstraint("(status = 'open' AND closed_at IS NULL AND counted_cash IS NULL AND expected_cash IS NULL AND difference IS NULL) OR (status = 'closed' AND closed_at IS NOT NULL AND closed_at >= opened_at AND counted_cash IS NOT NULL AND expected_cash IS NOT NULL AND difference IS NOT NULL AND difference = counted_cash - expected_cash)", name="ck_shift_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    staff_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    opening_cash: Mapped[int] = mapped_column(VND_DATABASE_TYPE, default=0)
    counted_cash: Mapped[int | None] = mapped_column(VND_DATABASE_TYPE)
    expected_cash: Mapped[int | None] = mapped_column(VND_DATABASE_TYPE)
    difference: Mapped[int | None] = mapped_column(VND_DATABASE_TYPE)
    status: Mapped[str] = mapped_column(String(8), default="open")


SHIFT_SQLITE_TRIGGERS = (
    "CREATE TRIGGER IF NOT EXISTS trg_shift_open_insert BEFORE INSERT ON cash_shifts WHEN NEW.status != 'open' BEGIN SELECT RAISE(ABORT, 'cash shift must start open'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_shift_immutable_update BEFORE UPDATE ON cash_shifts WHEN OLD.status = 'closed' OR NEW.id != OLD.id OR NEW.staff_id != OLD.staff_id OR NEW.opened_at != OLD.opened_at OR NEW.opening_cash != OLD.opening_cash BEGIN SELECT RAISE(ABORT, 'cash shift is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_shift_immutable_delete BEFORE DELETE ON cash_shifts BEGIN SELECT RAISE(ABORT, 'cash shift is immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_shift_integer_insert BEFORE INSERT ON cash_shifts WHEN typeof(NEW.opening_cash) != 'integer' OR (NEW.counted_cash IS NOT NULL AND typeof(NEW.counted_cash) != 'integer') BEGIN SELECT RAISE(ABORT, 'cash shift amount must be integer'); END",
    "CREATE TRIGGER IF NOT EXISTS trg_shift_integer_update BEFORE UPDATE ON cash_shifts WHEN (NEW.counted_cash IS NOT NULL AND typeof(NEW.counted_cash) != 'integer') OR (NEW.expected_cash IS NOT NULL AND typeof(NEW.expected_cash) != 'integer') OR (NEW.difference IS NOT NULL AND typeof(NEW.difference) != 'integer') BEGIN SELECT RAISE(ABORT, 'cash shift amount must be integer'); END",
)

SHIFT_SQLITE_CLOSE_TRIGGER = "CREATE TRIGGER IF NOT EXISTS trg_shift_close_balance BEFORE UPDATE ON cash_shifts WHEN NEW.status = 'closed' AND (NEW.expected_cash != NEW.opening_cash + COALESCE((SELECT SUM(CASE WHEN kind = 'receipt' THEN amount ELSE -amount END) FROM payments WHERE shift_id = NEW.id AND method = 'cash'), 0) OR EXISTS (SELECT 1 FROM payments WHERE shift_id = NEW.id AND created_at > NEW.closed_at)) BEGIN SELECT RAISE(ABORT, 'cash shift close balance invalid'); END"

SHIFT_POSTGRES_GUARD_SQL = """
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

for sql in SHIFT_SQLITE_TRIGGERS:
    event.listen(CashShift.__table__, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(CashShift.__table__, "after_create", DDL(SHIFT_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
event.listen(Base.metadata, "after_create", DDL(SHIFT_SQLITE_CLOSE_TRIGGER).execute_if(dialect="sqlite"))
