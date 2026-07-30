from typing import List, Optional
from datetime import datetime

from sqlalchemy import String, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_plate: Mapped[str] = mapped_column(String(20), unique=True)
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Quan hệ N-1: Một phương tiện được phân loại thành một loại xe cụ thể
    vehicle_type: Mapped["VehicleType"] = relationship(back_populates="vehicles")
    
    # Quan hệ N-1: Một phương tiện có thể thuộc về một khách hàng (Cho phép Null nếu là xe vãng lai)
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="vehicles")
    
    # Quan hệ 1-N: Một phương tiện có thể có nhiều hợp đồng vé tháng (theo các khoảng thời gian khác nhau)
    monthly_passes: Mapped[List["MonthlyPass"]] = relationship(back_populates="vehicle")
    
    # Quan hệ 1-N: Một phương tiện có thể có rất nhiều lượt gửi xe (Parking Sessions)
    parking_sessions: Mapped[List["ParkingSession"]] = relationship(back_populates="vehicle")