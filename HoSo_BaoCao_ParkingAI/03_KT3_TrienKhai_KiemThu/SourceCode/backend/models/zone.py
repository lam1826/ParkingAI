from typing import List
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    capacity: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "uq_zones_name_normalized",
            func.unicode_casefold(name),
            unique=True,
        ),
    )

    # Quan hệ 1-N: Một khu vực (Zone) bao gồm nhiều vị trí đỗ (Parking Slots)
    parking_slots: Mapped[List["ParkingSlot"]] = relationship(
        back_populates="zone",
        passive_deletes=True,
    )
