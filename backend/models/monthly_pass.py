from typing import List, Optional
from datetime import datetime, date

from sqlalchemy import DDL, Boolean, Date, ForeignKey, Index, String, event, text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import (
    Base,
    MONTHLY_PASS_DATE_RANGE_INSERT_TRIGGER_SQL,
    MONTHLY_PASS_DATE_RANGE_UPDATE_TRIGGER_SQL,
    MONTHLY_PASS_HISTORY_IMMUTABLE_TRIGGER_SQL,
    MONTHLY_PASS_PRICE_INSERT_TRIGGER_SQL,
    MONTHLY_PASS_PRICE_UPDATE_TRIGGER_SQL,
)
from core.money import VND_DATABASE_TYPE

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
            postgresql_where=text("pass_code IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    # Mã thẻ NFC/RFID — nullable để tương thích dữ liệu cũ; bản ghi mới bắt buộc qua API
    pass_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Số tiền thực thu (VND) — số nguyên, không dùng Float cho tiền tệ
    price: Mapped[int] = mapped_column(
        VND_DATABASE_TYPE,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
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


# API kiểm tra trước để trả lỗi 409 dễ hiểu, còn hai trigger này là backstop
# bắt buộc cho race condition và mọi đường ghi trực tiếp vào SQLite. Khoảng
# ngày là inclusive: hai vé chạm nhau tại cùng một ngày vẫn được xem là chồng.
event.listen(
    MonthlyPass.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER IF NOT EXISTS trg_monthly_passes_no_overlap_insert "
        "BEFORE INSERT ON monthly_passes FOR EACH ROW "
        "WHEN NEW.is_active = 1 AND EXISTS ("
        "SELECT 1 FROM monthly_passes "
        "WHERE vehicle_id = NEW.vehicle_id AND is_active = 1 "
        "AND start_date <= NEW.end_date AND end_date >= NEW.start_date) "
        "BEGIN SELECT RAISE(ABORT, 'monthly pass interval overlap'); END"
    ).execute_if(dialect="sqlite"),
)

event.listen(
    MonthlyPass.__table__,
    "after_create",
    DDL(MONTHLY_PASS_PRICE_INSERT_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    MonthlyPass.__table__,
    "after_create",
    DDL(MONTHLY_PASS_PRICE_UPDATE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    MonthlyPass.__table__,
    "after_create",
    DDL(MONTHLY_PASS_DATE_RANGE_INSERT_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    MonthlyPass.__table__,
    "after_create",
    DDL(MONTHLY_PASS_DATE_RANGE_UPDATE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)

# Trigger này tham chiếu parking_sessions nên chỉ cài sau khi toàn bộ metadata
# đã được tạo.
event.listen(
    Base.metadata,
    "after_create",
    DDL(MONTHLY_PASS_HISTORY_IMMUTABLE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)

event.listen(
    MonthlyPass.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER IF NOT EXISTS trg_monthly_passes_no_overlap_update "
        "BEFORE UPDATE OF vehicle_id, start_date, end_date, is_active "
        "ON monthly_passes FOR EACH ROW "
        "WHEN NEW.is_active = 1 AND EXISTS ("
        "SELECT 1 FROM monthly_passes "
        "WHERE id != OLD.id AND vehicle_id = NEW.vehicle_id AND is_active = 1 "
        "AND start_date <= NEW.end_date AND end_date >= NEW.start_date) "
        "BEGIN SELECT RAISE(ABORT, 'monthly pass interval overlap'); END"
    ).execute_if(dialect="sqlite"),
)
