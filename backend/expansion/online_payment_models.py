"""Durable provider identities and append-only evidence, separate from DEMO events."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DDL, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import VND_DATABASE_TYPE
from database import Base


class OnlinePaymentLink(Base):
    __tablename__ = "online_payment_links"
    __table_args__ = (
        CheckConstraint("id > 0 AND id <= 9007199254740991", name="ck_online_link_code"),
        CheckConstraint("amount > 0 AND amount <= 9007199254740991 AND currency='VND'", name="ck_online_link_amount"),
        CheckConstraint("state IN ('creating','unknown','ready','paid','cancelled','expired','review')", name="ck_online_link_state"),
        CheckConstraint("(order_id IS NOT NULL AND session_quote_id IS NULL) OR (order_id IS NULL AND session_quote_id IS NOT NULL)", name="ck_online_link_target"),
        Index("uq_online_payment_links_session_quote_id", "session_quote_id", unique=True),
    )
    # One durable code per frozen order. Never delete/reuse a code after ambiguous HTTP.
    id: Mapped[int] = mapped_column(VND_DATABASE_TYPE, primary_key=True, autoincrement=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("portal_orders.id"), unique=True)
    session_quote_id: Mapped[str | None] = mapped_column(ForeignKey("session_fee_quotes.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    receiver_digest: Mapped[str] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    currency: Mapped[str] = mapped_column(String(3), default="VND")
    description: Mapped[str] = mapped_column(String(9), default="PARKING")
    return_url: Mapped[str] = mapped_column(String(2048))
    cancel_url: Mapped[str] = mapped_column(String(2048))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    state: Mapped[str] = mapped_column(String(12), default="creating")
    provider_status: Mapped[str | None] = mapped_column(String(12))
    payment_link_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    checkout_url: Mapped[str | None] = mapped_column(String(2048))
    qr_code: Mapped[str | None] = mapped_column(Text)
    settled_reference: Mapped[str | None] = mapped_column(String(64))
    receipt_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), unique=True)
    review_reason: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(String(100))
    operation_token: Mapped[str | None] = mapped_column(String(36))
    operation_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)


class OnlinePaymentInbox(Base):
    __tablename__ = "online_payment_inbox"
    __table_args__ = (
        UniqueConstraint("channel", "reference", "payload_digest", name="uq_online_inbox_evidence"),
        CheckConstraint("amount > 0 AND amount <= 9007199254740991", name="ck_online_inbox_amount"),
        CheckConstraint("order_code > 0 AND order_code <= 9007199254740991", name="ck_online_inbox_code"),
        CheckConstraint("source IN ('webhook','reconcile')", name="ck_online_inbox_source"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Unknown order codes remain durable evidence; never manufacture a portal order.
    link_id: Mapped[int | None] = mapped_column(ForeignKey("online_payment_links.id"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(12))
    order_code: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    payment_link_id: Mapped[str] = mapped_column(String(64))
    reference: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    currency: Mapped[str] = mapped_column(String(3))
    receiver_digest: Mapped[str] = mapped_column(String(64))
    transaction_time: Mapped[str] = mapped_column(String(64))
    payload_digest: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    verification_issue: Mapped[str | None] = mapped_column(String(100))


class OnlinePaymentProcessing(Base):
    __tablename__ = "online_payment_processing"
    __table_args__ = (
        CheckConstraint("status IN ('received','processed','duplicate','review')", name="ck_online_processing_status"),
        CheckConstraint("attempts >= 0", name="ck_online_processing_attempts"),
        CheckConstraint("(status IN ('processed','duplicate') AND receipt_id IS NOT NULL) OR (status NOT IN ('processed','duplicate') AND receipt_id IS NULL)", name="ck_online_processing_receipt"),
        CheckConstraint("(status='received' AND processed_at IS NULL) OR (status!='received' AND processed_at IS NOT NULL)", name="ck_online_processing_time"),
    )
    id: Mapped[str] = mapped_column(ForeignKey("online_payment_inbox.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(12), default="received", index=True)
    reason: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    receipt_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)


class OnlinePaymentReviewDecision(Base):
    __tablename__ = "online_payment_review_decisions"
    __table_args__ = (
        UniqueConstraint("inbox_id", "request_id", name="uq_online_review_request"),
        CheckConstraint("action IN ('note','confirmed_external_refund')", name="ck_online_review_action"),
        CheckConstraint("length(trim(reason)) BETWEEN 3 AND 500 AND actor_id>0", name="ck_online_review_reason"),
        CheckConstraint("(action='note' AND refund_amount IS NULL AND external_reference IS NULL) OR (action='confirmed_external_refund' AND refund_amount>0 AND refund_amount<=9007199254740991 AND length(trim(external_reference)) BETWEEN 3 AND 120)", name="ck_online_review_refund"),
        # Two differing inbox payloads for one bank reference cannot be refunded twice.
        Index("uq_online_review_final_reference", "channel", "payment_reference", unique=True,
            sqlite_where=text("action='confirmed_external_refund'"), postgresql_where=text("action='confirmed_external_refund'")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    inbox_id: Mapped[str] = mapped_column(ForeignKey("online_payment_inbox.id"), index=True)
    channel: Mapped[str] = mapped_column(String(64))
    payment_reference: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[int] = mapped_column(Integer)
    actor_username: Mapped[str] = mapped_column(String(50))
    refund_amount: Mapped[int | None] = mapped_column(VND_DATABASE_TYPE)
    external_reference: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


from expansion.online_payment_guards import ONLINE_PAYMENT_SQLITE_GUARDS, ONLINE_PAYMENT_POSTGRES_GUARD_SQL

for sql in ONLINE_PAYMENT_SQLITE_GUARDS.values():
    event.listen(Base.metadata, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(ONLINE_PAYMENT_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
