from typing import List
from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Quan hệ N-1: Một User thuộc về một Role
    role: Mapped["Role"] = relationship(back_populates="users")
    
    # --- Các quan hệ khác theo thiết kế ERD tổng thể của hệ thống ---
    
    # Quan hệ 1-N: Một nhân viên có thể check-in cho nhiều lượt gửi xe
    parking_sessions_in: Mapped[List["ParkingSession"]] = relationship(
        foreign_keys="[ParkingSession.staff_in_id]", back_populates="staff_in"
    )
    
    # Quan hệ 1-N: Một nhân viên có thể check-out cho nhiều lượt gửi xe
    parking_sessions_out: Mapped[List["ParkingSession"]] = relationship(
        foreign_keys="[ParkingSession.staff_out_id]", back_populates="staff_out"
    )
    
    # Quan hệ 1-N: Một nhân viên có thể yêu cầu sinh nhiều báo cáo AI
    ai_reports: Mapped[List["AiReport"]] = relationship(back_populates="generated_by")