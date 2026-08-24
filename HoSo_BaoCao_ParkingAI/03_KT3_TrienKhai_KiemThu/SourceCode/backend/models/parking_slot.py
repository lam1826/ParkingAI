from typing import List
from datetime import datetime

from sqlalchemy import String, Boolean, DDL, ForeignKey, Index, event
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

    __table_args__ = (
        Index(
            "uq_parking_slots_name_normalized",
            func.unicode_casefold(slot_name),
            unique=True,
        ),
    )

    # Quan hệ N-1: Một vị trí đỗ thuộc về một khu vực
    zone: Mapped["Zone"] = relationship(back_populates="parking_slots")
    
    # Quan hệ N-1: Một vị trí đỗ được quy định dành cho một loại xe cụ thể
    vehicle_type: Mapped["VehicleType"] = relationship(back_populates="parking_slots")
    
    # Quan hệ 1-N: Một vị trí đỗ có thể trải qua nhiều lượt gửi xe theo thời gian
    parking_sessions: Mapped[List["ParkingSession"]] = relationship(
        back_populates="slot",
        passive_deletes=True,
    )


# Backstop SQLite cho bất biến Zone.capacity. Router kiểm tra trước để trả
# thông báo nghiệp vụ rõ ràng; trigger bắt race giữa hai request và mọi đường
# ghi trực tiếp vào DB. Migration tương ứng nằm trong database.py cho DB cũ.
event.listen(
    ParkingSlot.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_parking_slots_capacity_insert
        BEFORE INSERT ON parking_slots
        FOR EACH ROW
        WHEN (
            SELECT COUNT(*) FROM parking_slots WHERE zone_id = NEW.zone_id
        ) >= COALESCE((
            SELECT capacity FROM zones WHERE id = NEW.zone_id
        ), 0)
        BEGIN
            SELECT RAISE(ABORT, 'zone capacity exceeded');
        END
        """
    ).execute_if(dialect="sqlite"),
)

event.listen(
    ParkingSlot.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_parking_slots_capacity_move
        BEFORE UPDATE OF zone_id ON parking_slots
        FOR EACH ROW
        WHEN NEW.zone_id != OLD.zone_id AND (
            SELECT COUNT(*) FROM parking_slots WHERE zone_id = NEW.zone_id
        ) >= COALESCE((
            SELECT capacity FROM zones WHERE id = NEW.zone_id
        ), 0)
        BEGIN
            SELECT RAISE(ABORT, 'zone capacity exceeded');
        END
        """
    ).execute_if(dialect="sqlite"),
)

event.listen(
    ParkingSlot.__table__,
    "after_create",
    DDL(
        """
        CREATE TRIGGER IF NOT EXISTS trg_zones_capacity_update
        BEFORE UPDATE OF capacity ON zones
        FOR EACH ROW
        WHEN NEW.capacity < (
            SELECT COUNT(*) FROM parking_slots WHERE zone_id = OLD.id
        )
        BEGIN
            SELECT RAISE(ABORT, 'zone capacity below slot count');
        END
        """
    ).execute_if(dialect="sqlite"),
)
