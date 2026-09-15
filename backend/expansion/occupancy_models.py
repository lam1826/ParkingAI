"""Versioned image calibration and observational CV results; no parking writes."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from database import Base


class OccupancyCalibration(Base):
    __tablename__ = "occupancy_calibrations"
    __table_args__ = (
        UniqueConstraint("camera_id", "version", name="uq_occupancy_camera_version"),
        UniqueConstraint("camera_id", "request_id", name="uq_occupancy_calibration_request"),
        CheckConstraint("version > 0", name="ck_occupancy_calibration_version"),
        CheckConstraint("settings_schema_version = 1", name="ck_occupancy_settings_version"),
        CheckConstraint("engine = 'reference-diff-v1'", name="ck_occupancy_calibration_engine"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("vision_cameras.id"), index=True)
    version: Mapped[int]
    reference_observation_id: Mapped[str | None] = mapped_column(ForeignKey("vision_observations.id", ondelete="SET NULL"))
    reference_id_snapshot: Mapped[str] = mapped_column(String(36))
    reference_image_hash: Mapped[str] = mapped_column(String(64))
    reference_width: Mapped[int]
    reference_height: Mapped[int]
    reference_observed_at: Mapped[datetime] = mapped_column(DateTime)
    reference_expires_at: Mapped[datetime] = mapped_column(DateTime)
    engine: Mapped[str] = mapped_column(String(40), default="reference-diff-v1")
    settings_schema_version: Mapped[int] = mapped_column(default=1)
    regions: Mapped[list] = mapped_column(JSON)
    settings: Mapped[dict] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)


class OccupancyCalibrationSlot(Base):
    """Retain the physical slot identity even if a former calibration is superseded."""
    __tablename__ = "occupancy_calibration_slots"
    calibration_id: Mapped[str] = mapped_column(ForeignKey("occupancy_calibrations.id"), primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"), primary_key=True, index=True)


class OccupancyObservation(Base):
    __tablename__ = "occupancy_observations"
    __table_args__ = (
        UniqueConstraint("calibration_id", "source_id_snapshot", name="uq_occupancy_calibration_source"),
        CheckConstraint("engine = 'reference-diff-v1'", name="ck_occupancy_observation_engine"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    calibration_id: Mapped[str] = mapped_column(ForeignKey("occupancy_calibrations.id"), index=True)
    source_observation_id: Mapped[str | None] = mapped_column(ForeignKey("vision_observations.id", ondelete="SET NULL"))
    source_id_snapshot: Mapped[str] = mapped_column(String(36))
    source_image_hash: Mapped[str] = mapped_column(String(64))
    measured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    analyzed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    engine: Mapped[str] = mapped_column(String(40), default="reference-diff-v1")
    quality: Mapped[dict] = mapped_column(JSON)
    readings: Mapped[list] = mapped_column(JSON)
