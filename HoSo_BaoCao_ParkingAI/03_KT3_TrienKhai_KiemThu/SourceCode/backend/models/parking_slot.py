from typing import List
from datetime import datetime

from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class ParkingSlot(Base):
    __tablename__ = "parking_slots"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    slot_name: Mapped[str] = mapped_column(String(50))
    is_occupied: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Quan hệ N-1: Một vị trí đỗ thuộc về một khu vực
    zone: Mapped["Zone"] = relationship(back_populates="parking_slots")
    
    # Quan hệ N-1: Một vị trí đỗ được quy định dành cho một loại xe cụ thể
    vehicle_type: Mapped["VehicleType"] = relationship(back_populates="parking_slots")
    
    # Quan hệ 1-N: Một vị trí đỗ có thể trải qua nhiều lượt gửi xe theo thời gian
    parking_sessions: Mapped[List["ParkingSession"]] = relationship(back_populates="slot")