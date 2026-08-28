from typing import List, Optional
from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base, UQ_CUSTOMERS_PHONE_NORMALIZED

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    phone_number: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            UQ_CUSTOMERS_PHONE_NORMALIZED,
            func.unicode_casefold(phone_number),
            unique=True,
        ),
    )

    # Quan hệ 1-N: Một khách hàng có thể đăng ký/sở hữu nhiều xe
    vehicles: Mapped[List["Vehicle"]] = relationship(back_populates="customer")
    
    # Quan hệ 1-N: Một khách hàng có thể thanh toán/sở hữu nhiều vé tháng
    monthly_passes: Mapped[List["MonthlyPass"]] = relationship(back_populates="customer")
