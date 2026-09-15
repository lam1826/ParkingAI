"""Capacity leases and single-use prepaid parking entitlements."""
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.money import VND_DATABASE_TYPE
from database import Base


class ParkingCapacityHold(Base):
    __tablename__ = "parking_capacity_holds"
    __table_args__ = (
        CheckConstraint("status IN ('held','converted','released','expired')", name="ck_capacity_hold_status"),
        CheckConstraint("end_at>start_at AND expires_at<=end_at", name="ck_capacity_hold_window"),
        Index("ix_capacity_hold_slot_window", "slot_id", "start_at", "end_at"),
        Index("ix_capacity_hold_due", "status", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("portal_orders.id"), unique=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default="held")
    reservation_id: Mapped[str | None] = mapped_column(ForeignKey("parking_reservations.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class TimedParkingPass(Base):
    __tablename__ = "timed_parking_passes"
    __table_args__ = (
        CheckConstraint("status IN ('ready','consumed','expired','revoked')", name="ck_timed_pass_status"),
        CheckConstraint("end_at>start_at AND arrival_deadline>=start_at AND arrival_deadline<=end_at", name="ck_timed_pass_window"),
        CheckConstraint("amount>0 AND rate_unit_price>=0 AND rate_ticket_type IN ('HOURLY','DAILY')", name="ck_timed_pass_money"),
        Index("ix_timed_pass_customer", "customer_id", "start_at"),
        Index("ix_timed_pass_vehicle", "vehicle_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("portal_orders.id"), unique=True)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("parking_reservations.id"), unique=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    arrival_deadline: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    rate_config_id: Mapped[int] = mapped_column()
    rate_ticket_type: Mapped[str] = mapped_column(String(8))
    rate_unit_price: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    rate_effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="ready")
    session_id: Mapped[str | None] = mapped_column(ForeignKey("parking_sessions.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
