"""Operational exceptions retain their original admission and actor evidence."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DDL, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from core.clock import business_now
from core.session_event_guards import SESSION_EVENT_POSTGRES_GUARD_SQL, SESSION_EVENT_SQLITE_GUARDS
from database import Base


class ParkingSessionEvent(Base):
    __tablename__ = "parking_session_events"
    __table_args__ = (
        UniqueConstraint("session_id", "request_id", name="uq_session_event_request"),
        CheckConstraint("action IN ('cancelled','lost_ticket','plate_corrected')", name="ck_session_event_action"),
        CheckConstraint("length(trim(reason)) BETWEEN 3 AND 500", name="ck_session_event_reason"),
        CheckConstraint("length(trim(request_id)) BETWEEN 1 AND 64", name="ck_session_event_request"),
        CheckConstraint("actor_id > 0 AND length(trim(actor_username)) > 0", name="ck_session_event_actor"),
        CheckConstraint("(action='plate_corrected' AND replacement_session_id IS NOT NULL AND replacement_session_id != session_id) OR (action!='plate_corrected' AND replacement_session_id IS NULL)", name="ck_session_event_replacement"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("parking_sessions.id"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("parking_sites.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    request_id: Mapped[str] = mapped_column(String(64))
    # Snapshot identity survives later account removal/renaming.
    actor_id: Mapped[int] = mapped_column(Integer)
    actor_username: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now)
    before_state: Mapped[dict] = mapped_column(JSON)
    after_state: Mapped[dict] = mapped_column(JSON)
    replacement_session_id: Mapped[str | None] = mapped_column(ForeignKey("parking_sessions.id"), index=True)


for sql in SESSION_EVENT_SQLITE_GUARDS.values():
    event.listen(Base.metadata, "after_create", DDL(sql).execute_if(dialect="sqlite"))
event.listen(Base.metadata, "after_create", DDL(SESSION_EVENT_POSTGRES_GUARD_SQL).execute_if(dialect="postgresql"))
