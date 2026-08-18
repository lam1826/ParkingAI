from datetime import datetime, date

from sqlalchemy import String, Float, Boolean, Date, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class PriceConfig(Base):
    __tablename__ = "price_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    ticket_type: Mapped[str] = mapped_column(String(20))  # Ví dụ: 'HOURLY', 'DAILY', 'MONTHLY'
    price: Mapped[float] = mapped_column(Float)
    effective_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Quan hệ N-1: Một cấu hình giá được áp dụng cho một loại phương tiện (Vehicle Type) cụ thể
    vehicle_type: Mapped["VehicleType"] = relationship(back_populates="price_configs")