"""Scoped AI history is separate from unassigned legacy reports."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from core.clock import business_now
from database import Base


class SiteAiAnalysis(Base):
    __tablename__ = "site_ai_analyses"
    __table_args__ = (
        UniqueConstraint("generated_by_id", "request_id", name="uq_site_ai_request"),
        Index("ix_site_ai_history", "site_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("parking_sites.id"), nullable=False)
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=business_now, nullable=False)
