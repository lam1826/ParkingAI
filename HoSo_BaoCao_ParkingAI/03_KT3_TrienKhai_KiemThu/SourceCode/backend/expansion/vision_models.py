"""Private, short-lived observations; recognizing a plate never moves a vehicle."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from database import Base


class Camera(Base):
    __tablename__ = "vision_cameras"
    __table_args__ = (
        CheckConstraint("direction IN ('entry','exit')", name="ck_camera_direction"),
        CheckConstraint("retention_hours BETWEEN 1 AND 72", name="ck_camera_retention"),
        UniqueConstraint("site_id", "name", name="uq_camera_site_name"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"))
    name: Mapped[str] = mapped_column(String(100))
    direction: Mapped[str] = mapped_column(String(8), default="entry")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_hours: Mapped[int] = mapped_column(default=24)
    edge_token_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class VisionObservation(Base):
    __tablename__ = "vision_observations"
    __table_args__ = (
        UniqueConstraint("camera_id", "event_id", name="uq_vision_camera_event"),
        CheckConstraint("review_status IN ('pending','accepted','rejected')", name="ck_vision_review_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id: Mapped[int] = mapped_column(ForeignKey("vision_cameras.id"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36))
    image_hash: Mapped[str] = mapped_column(String(64))
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    image_width: Mapped[int]
    image_height: Mapped[int]
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    captured_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ocr_status: Mapped[str] = mapped_column(String(20))
    suggested_plate: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    detections: Mapped[list] = mapped_column(JSON, default=list)
    engine: Mapped[str] = mapped_column(String(50))
    review_status: Mapped[str] = mapped_column(String(10), default="pending")
    confirmed_plate: Mapped[str | None] = mapped_column(String(20))
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
