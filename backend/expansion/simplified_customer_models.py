"""Declared booking and narrow ticket-payment authority are not vehicle ownership."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from database import Base


class SessionTicketCredential(Base):
    __tablename__ = 'session_ticket_credentials'
    session_id: Mapped[str] = mapped_column(ForeignKey('parking_sessions.id'), primary_key=True)
    version: Mapped[str] = mapped_column(String(32), default=lambda: uuid.uuid4().hex)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class SessionPaymentAccess(Base):
    __tablename__ = 'session_payment_access'
    __table_args__ = (
        UniqueConstraint('user_id', 'session_id', name='uq_session_payment_access_user_session'),
        CheckConstraint('expires_at>created_at', name='ck_session_payment_access_expiry'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('parking_sessions.id'), index=True)
    credential_version: Mapped[str] = mapped_column(String(32))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey('vehicles.id'))
    customer_snapshot_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)


class DeclaredParkingReservation(Base):
    __tablename__ = 'declared_parking_reservations'
    __table_args__ = (
        UniqueConstraint('user_id', 'request_id', name='uq_declared_booking_request'),
        CheckConstraint('end_at>start_at AND arrival_deadline>start_at AND arrival_deadline<=end_at', name='ck_declared_booking_interval'),
        CheckConstraint("status IN ('confirmed','arrived','cancelled','expired')", name='ck_declared_booking_status'),
        Index('ix_declared_booking_slot_interval', 'slot_id', 'start_at', 'end_at'),
        Index('ix_declared_booking_plate_interval', 'normalized_plate', 'start_at', 'end_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[int] = mapped_column(ForeignKey('parking_sites.id'), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey('parking_slots.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    license_plate: Mapped[str] = mapped_column(String(20))
    normalized_plate: Mapped[str] = mapped_column(String(20))
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey('vehicle_types.id'))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    arrival_deadline: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12), default='confirmed')
    session_id: Mapped[str | None] = mapped_column(ForeignKey('parking_sessions.id'), unique=True)
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
