from typing import List, Optional
from datetime import datetime, date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class MonthlyPass(Base):
    __tablename__ = "monthly_passes"

    # Unique partial index: pass_code phải duy nhất toàn hệ thống, nhưng các bản
    # ghi cũ (NULL, tạo trước khi có cột) không đụng độ nhau. Tên index phải khớp
    # với migration ALTER trong database.py để không tạo trùng.
    __table_args__ = (
        Index(
            "ix_monthly_passes_pass_code",
            "pass_code",
            unique=True,
            sqlite_where=text("pass_code IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    # Mã thẻ NFC/RFID — nullable để tương thích dữ liệu cũ; bản ghi mới bắt buộc qua API
    pass_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Số tiền thực thu (VND) — số nguyên, không dùng Float cho tiền tệ
    price: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
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