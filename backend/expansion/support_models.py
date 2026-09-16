"""Customer support threads and receipt-based refund requests.

A refund request always points at the original receipt row in ``payments``;
the amount a customer may ask for is computed on the server from that receipt
and its compensating refunds, never taken from the client. Decisions are
recorded in place with actor/time, and the actual money movement is the
``payments`` refund row referenced by ``refund_payment_id``.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import VND_DATABASE_TYPE
from database import Base


def uid():
    return str(uuid.uuid4())


SUPPORT_CATEGORIES = ("general", "order", "session", "receipt", "refund")
SUPPORT_LINK_TYPES = ("order", "session", "receipt", "refund_request")
SUPPORT_STATES = ("open", "answered", "closed")
REFUND_STATES = ("pending", "reviewing", "approved", "rejected", "refunded")
REFUND_OPEN_STATES = ("pending", "reviewing", "approved")
REFUND_CHANNELS = ("demo", "counter", "online", "legacy")


class CustomerSupportRequest(Base):
    __tablename__ = "customer_support_requests"
    __table_args__ = (
        CheckConstraint("category IN ('general','order','session','receipt','refund')", name="ck_support_request_category"),
        CheckConstraint("status IN ('open','answered','closed')", name="ck_support_request_status"),
        CheckConstraint("(linked_type IS NULL AND linked_id IS NULL) OR (linked_type IN ('order','session','receipt','refund_request') AND linked_id IS NOT NULL)", name="ck_support_request_link"),
        CheckConstraint("length(trim(subject)) BETWEEN 3 AND 150", name="ck_support_request_subject"),
        CheckConstraint("status != 'closed' OR (closed_at IS NOT NULL AND closed_by_id IS NOT NULL)", name="ck_support_request_closed"),
        Index("ix_support_request_site_status", "site_id", "status", "last_message_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(16), default="general")
    status: Mapped[str] = mapped_column(String(12), default="open")
    linked_type: Mapped[str | None] = mapped_column(String(16))
    linked_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class CustomerSupportMessage(Base):
    __tablename__ = "customer_support_messages"
    __table_args__ = (
        CheckConstraint("author_role IN ('customer','staff','manager','admin')", name="ck_support_message_role"),
        CheckConstraint("length(trim(body)) BETWEEN 1 AND 2000", name="ck_support_message_body"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("customer_support_requests.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author_role: Mapped[str] = mapped_column(String(12))
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class PaymentRefundRequest(Base):
    __tablename__ = "payment_refund_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending','reviewing','approved','rejected','refunded')", name="ck_refund_request_status"),
        CheckConstraint("payment_channel IN ('demo','counter','online','legacy')", name="ck_refund_request_channel"),
        CheckConstraint("requested_amount > 0 AND requested_amount <= 9007199254740991", name="ck_refund_request_amount"),
        CheckConstraint("approved_amount IS NULL OR (approved_amount > 0 AND approved_amount <= requested_amount)", name="ck_refund_request_approved"),
        CheckConstraint("status NOT IN ('approved','refunded') OR approved_amount IS NOT NULL", name="ck_refund_request_approved_amount"),
        CheckConstraint("status NOT IN ('approved','rejected','refunded') OR (reviewed_at IS NOT NULL AND reviewed_by_id IS NOT NULL)", name="ck_refund_request_reviewed"),
        CheckConstraint("(status = 'refunded' AND refund_payment_id IS NOT NULL AND refunded_at IS NOT NULL AND refunded_by_id IS NOT NULL AND refund_method IS NOT NULL) OR (status != 'refunded' AND refund_payment_id IS NULL AND refunded_at IS NULL)", name="ck_refund_request_refunded"),
        Index("uq_payment_refund_open", "receipt_id", unique=True,
              sqlite_where=text("status IN ('pending','reviewing','approved')"),
              postgresql_where=text("status IN ('pending','reviewing','approved')")),
        Index("ix_refund_request_site_status", "site_id", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    receipt_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sites.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_type: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[str] = mapped_column(String(36))
    payment_channel: Mapped[str] = mapped_column(String(8))
    receipt_method: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(500))
    requested_amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    approved_amount: Mapped[int | None] = mapped_column(VND_DATABASE_TYPE)
    decision_note: Mapped[str] = mapped_column(String(500), default="")
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    refund_payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), unique=True)
    refund_method: Mapped[str | None] = mapped_column(String(16))
    external_reference: Mapped[str | None] = mapped_column(String(120))
    refunded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
