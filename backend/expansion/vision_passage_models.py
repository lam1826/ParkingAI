"""Opt-in camera rules and durable decisions, without retaining private images."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from database import Base


class CameraAutomationPolicy(Base):
    __tablename__ = "vision_automation_policies"
    __table_args__ = (
        CheckConstraint("minimum_confidence >= 0.9 AND minimum_confidence <= 1", name="ck_vision_auto_confidence"),
        CheckConstraint("max_age_seconds BETWEEN 3 AND 30", name="ck_vision_auto_age"),
        CheckConstraint("direction IN ('entry','exit')", name="ck_vision_auto_direction"),
    )
    camera_id: Mapped[int] = mapped_column(ForeignKey("vision_cameras.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    minimum_confidence: Mapped[float] = mapped_column(Float, default=0.97)
    max_age_seconds: Mapped[int] = mapped_column(default=15)
    direction: Mapped[str] = mapped_column(String(8))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class VisionPassageEvent(Base):
    __tablename__ = "vision_passage_events"
    __table_args__ = (
        UniqueConstraint("camera_id", "event_id", name="uq_vision_passage_camera_event"),
        UniqueConstraint("observation_key", name="uq_vision_passage_observation"),
        CheckConstraint("direction IN ('entry','exit')", name="ck_vision_passage_direction"),
        CheckConstraint("state IN ('entered','exited','already_entered','waiting_payment','manual','disabled')", name="ck_vision_passage_state"),
        Index("ix_vision_passage_site_time", "site_id", "processed_at"),
        Index("ix_vision_passage_plate_time", "site_id", "plate_key", "processed_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id: Mapped[int] = mapped_column(ForeignKey("vision_cameras.id"))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"))
    observation_id: Mapped[str | None] = mapped_column(ForeignKey("vision_observations.id", ondelete="SET NULL"))
    observation_key: Mapped[str] = mapped_column(String(36))
    event_id: Mapped[str] = mapped_column(String(36))
    direction: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(20))
    license_plate: Mapped[str | None] = mapped_column(String(20))
    plate_key: Mapped[str | None] = mapped_column(String(20))
    vehicle_type_id: Mapped[int | None] = mapped_column(ForeignKey("vehicle_types.id"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("parking_sessions.id"))
    reason: Mapped[str] = mapped_column(String(500))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    captured_at: Mapped[datetime] = mapped_column(DateTime)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
