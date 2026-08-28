from typing import List, Optional
from datetime import datetime

from sqlalchemy import Boolean, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class VehicleType(Base):
    __tablename__ = "vehicle_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "uq_vehicle_types_name_normalized",
            func.unicode_casefold(name),
            unique=True,
        ),
    )

    # Quan hệ 1-N: Một loại xe có nhiều xe cụ thể (Vehicles)
    vehicles: Mapped[List["Vehicle"]] = relationship(back_populates="vehicle_type")
    
    # Quan hệ 1-N: Một loại xe có thể được quy định cho nhiều vị trí đỗ (Parking Slots)
    parking_slots: Mapped[List["ParkingSlot"]] = relationship(back_populates="vehicle_type")
    
    # Quan hệ 1-N: Một loại xe có nhiều cấu hình giá (Price Configs) theo từng thời điểm/loại vé
    price_configs: Mapped[List["PriceConfig"]] = relationship(back_populates="vehicle_type")
