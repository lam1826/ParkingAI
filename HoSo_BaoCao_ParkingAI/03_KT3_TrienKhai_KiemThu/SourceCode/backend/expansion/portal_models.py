"""Customer authority and immutable order snapshots; no historical ownership backfill."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import VND_DATABASE_TYPE
from database import Base


def uid():
    return str(uuid.uuid4())


class PortalAccountLink(Base):
    __tablename__ = "portal_account_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), unique=True)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verification: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class PortalLinkRequest(Base):
    __tablename__ = "portal_link_requests"
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected')", name="ck_portal_link_state"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    phone_number: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(12), default="pending")
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class PortalVehicleRequest(Base):
    __tablename__ = "portal_vehicle_requests"
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected')", name="ck_portal_vehicle_request_state"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    license_plate: Mapped[str] = mapped_column(String(20))
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(12), default="pending")
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class PortalVehicleOwnership(Base):
    __tablename__ = "portal_vehicle_ownerships"
    __table_args__ = (UniqueConstraint("customer_id", "vehicle_id", name="uq_portal_vehicle_owner"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    approved_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class PortalSessionGrant(Base):
    __tablename__ = "portal_session_grants"
    parking_session_id: Mapped[str] = mapped_column(ForeignKey("parking_sessions.id"), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("price > 0 AND price <= 9007199254740991", name="ck_portal_plan_price"),
        CheckConstraint("duration_days >= 1 AND duration_days <= 366", name="ck_portal_plan_duration"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    duration_days: Mapped[int] = mapped_column()
    price: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PortalOrder(Base):
    __tablename__ = "portal_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_portal_order_request"),
        CheckConstraint("amount > 0 AND amount <= 9007199254740991", name="ck_portal_order_amount"),
        CheckConstraint("end_date >= start_date", name="ck_portal_order_dates"),
        CheckConstraint("payment_mode IN ('demo','manual')", name="ck_portal_order_mode"),
        CheckConstraint("status IN ('pending','fulfilled','failed','cancelled','expired','review','refunded')", name="ck_portal_order_state"),
        CheckConstraint("status NOT IN ('fulfilled','refunded') OR (monthly_pass_id IS NOT NULL AND receipt_id IS NOT NULL)", name="ck_portal_order_fulfilled"),
        Index("ix_portal_order_due", "status", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("subscription_plans.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("parking_cards.id"))
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    payment_mode: Mapped[str] = mapped_column(String(8), default="demo")
    status: Mapped[str] = mapped_column(String(12), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(64))
    demo_token: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    monthly_pass_id: Mapped[int | None] = mapped_column(ForeignKey("monthly_passes.id"), unique=True)
    receipt_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), unique=True)
    review_reason: Mapped[str | None] = mapped_column(String(100))


class PortalPaymentEvent(Base):
    __tablename__ = "portal_payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "reference", name="uq_portal_provider_reference"),
        CheckConstraint("outcome IN ('success','failed','cancelled')", name="ck_portal_event_outcome"),
        CheckConstraint("status IN ('received','processed','review')", name="ck_portal_event_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("portal_orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(12), default="demo")
    reference: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default="received")
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(100))


class PortalNotification(Base):
    __tablename__ = "portal_notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True)
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)


class PortalRefundRequest(Base):
    __tablename__ = "portal_refund_requests"
    __table_args__ = (CheckConstraint("status IN ('pending','approved','rejected')", name="ck_portal_refund_state"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("portal_orders.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(12), default="pending")
    note: Mapped[str] = mapped_column(String(500), default="")
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    refund_payment_id: Mapped[str | None] = mapped_column(ForeignKey("payments.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
