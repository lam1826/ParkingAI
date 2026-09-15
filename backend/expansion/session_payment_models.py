"""Frozen accrued-fee proposals and immutable online credits; no automatic exit."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DDL, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import VND_DATABASE_TYPE
from database import Base


class SessionFeeQuote(Base):
    __tablename__ = "session_fee_quotes"
    __table_args__ = (
        UniqueConstraint("created_by_id", "session_id", "request_id", name="uq_session_fee_quote_request"),
        CheckConstraint("status IN ('pending','fulfilled','cancelled','expired','review')", name="ck_session_fee_quote_status"),
        CheckConstraint("gross_fee>0 AND gross_fee<=9007199254740991 AND credited_amount>=0 AND amount>0 AND amount=gross_fee-credited_amount", name="ck_session_fee_quote_money"),
        CheckConstraint("expires_at>quoted_at AND paid_through>=quoted_at", name="ck_session_fee_quote_time"),
        CheckConstraint("status!='fulfilled' OR (credit_id IS NOT NULL AND receipt_id IS NOT NULL)", name="ck_session_fee_quote_fulfilled"),
        Index("uq_session_fee_pending", "session_id", unique=True,
            sqlite_where=text("status='pending'"), postgresql_where=text("status='pending'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("parking_sessions.id"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    owner_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    request_id: Mapped[str] = mapped_column(String(64))
    session_state_hash: Mapped[str] = mapped_column(String(64))
    credit_snapshot_hash: Mapped[str] = mapped_column(String(64))
    gross_fee: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    credited_amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    quoted_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    paid_through: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    billing_basis: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    review_reason: Mapped[str | None] = mapped_column(String(100))
    # Reverse pointers are enforced by guards without circular CREATE TABLE FKs.
    credit_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    receipt_id: Mapped[str | None] = mapped_column(String(36), unique=True)

    @property
    def payment_mode(self):
        return "payos"

    @property
    def customer_id(self):
        return self.owner_customer_id


class SessionFeeCredit(Base):
    __tablename__ = "session_fee_credits"
    __table_args__ = (
        CheckConstraint("amount>0 AND amount<=9007199254740991", name="ck_session_fee_credit_money"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("parking_sessions.id"), index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("session_fee_quotes.id"), unique=True)
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    paid_through: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    receipt_id: Mapped[str | None] = mapped_column(String(36), unique=True)


from expansion.session_payment_guards import SESSION_PAYMENT_SQLITE_GUARDS, SESSION_PAYMENT_POSTGRES_GUARD_SQL

for sql in SESSION_PAYMENT_SQLITE_GUARDS.values():
    event.listen(Base.metadata, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(SESSION_PAYMENT_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
