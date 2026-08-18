from typing import List
from datetime import datetime, date

from sqlalchemy import Boolean, Date, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class MonthlyPass(Base):
    __tablename__ = "monthly_passes"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Quan hệ N-1: Một vé tháng do một khách hàng (Customer) thanh toán/đăng ký
    customer: Mapped["Customer"] = relationship(back_populates="monthly_passes")
    
    # Quan hệ N-1: Một vé tháng áp dụng cho một chiếc xe (Vehicle) cụ thể
    vehicle: Mapped["Vehicle"] = relationship(back_populates="monthly_passes")
    
    # Quan hệ 1-N: Một vé tháng có thể được sử dụng để xác thực cho nhiều lượt gửi xe (Parking Sessions)
    parking_sessions: Mapped[List["ParkingSession"]] = relationship(back_populates="monthly_pass")