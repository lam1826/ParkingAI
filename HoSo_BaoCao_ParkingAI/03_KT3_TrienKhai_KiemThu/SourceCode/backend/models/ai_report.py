from datetime import datetime

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class AiReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(50))  # Ví dụ: 'REVENUE', 'TRAFFIC', 'ANOMALY'
    prompt_used: Mapped[str] = mapped_column(Text)        # Câu lệnh người dùng đã hỏi AI
    content: Mapped[str] = mapped_column(Text)            # Nội dung báo cáo do AI sinh ra (JSON hoặc Text)
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # --- Các Quan hệ (Relationships) ---
    
    # Quan hệ N-1: Một báo cáo AI được yêu cầu và sinh ra bởi một người dùng (User/Admin)
    generated_by: Mapped["User"] = relationship(back_populates="ai_reports")