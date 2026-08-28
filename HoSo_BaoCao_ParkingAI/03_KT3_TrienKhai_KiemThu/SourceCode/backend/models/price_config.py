from datetime import datetime, date

from sqlalchemy import DDL, String, Boolean, Date, ForeignKey, Index, event, text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import (
    Base,
    PRICE_INTEGER_INSERT_TRIGGER_SQL,
    PRICE_INTEGER_UPDATE_TRIGGER_SQL,
    PRICE_SAFE_VND_INSERT_TRIGGER_SQL,
    PRICE_SAFE_VND_UPDATE_TRIGGER_SQL,
    PRICE_TICKET_TYPE_INSERT_TRIGGER_SQL,
    PRICE_TICKET_TYPE_UPDATE_TRIGGER_SQL,
    PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL,
    PRICE_EFFECTIVE_DATE_UPDATE_TRIGGER_SQL,
    PRICE_ACTIVE_SESSION_DELETE_GUARD_TRIGGER_SQL,
    PRICE_ACTIVE_SESSION_REPLACE_GUARD_TRIGGER_SQL,
    PRICE_ACTIVE_SESSION_UPDATE_GUARD_TRIGGER_SQL,
)
from core.money import VND_DATABASE_TYPE

class PriceConfig(Base):
    __tablename__ = "price_configs"

    # Backstop ở tầng DB cho bất biến nghiệp vụ: mỗi loại xe chỉ có tối đa MỘT
    # bảng giá active (không phân biệt ticket_type). Partial index nên nhiều
    # bản ghi inactive cùng loại xe vẫn được phép. Router đã chặn trước và trả
    # 409; index này bắt các đường ghi khác (script seed, sửa DB tay, hai
    # request đồng thời) — IntegrityError được main.py chuyển thành 409.
    # Tên index phải khớp câu lệnh trong database.py::run_sqlite_migrations.
    __table_args__ = (
        Index(
            "uq_price_config_one_active_per_vehicle_type",
            "vehicle_type_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"))
    ticket_type: Mapped[str] = mapped_column(String(20))  # HOURLY hoặc DAILY
    price: Mapped[int] = mapped_column(VND_DATABASE_TYPE)
    effective_date: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # Quan hệ N-1: Một cấu hình giá được áp dụng cho một loại phương tiện (Vehicle Type) cụ thể
    vehicle_type: Mapped["VehicleType"] = relationship(back_populates="price_configs")


event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_INTEGER_INSERT_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_SAFE_VND_INSERT_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_SAFE_VND_UPDATE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_TICKET_TYPE_INSERT_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_TICKET_TYPE_UPDATE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_INTEGER_UPDATE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL).execute_if(dialect="sqlite"),
)
event.listen(
    PriceConfig.__table__,
    "after_create",
    DDL(PRICE_EFFECTIVE_DATE_UPDATE_TRIGGER_SQL).execute_if(dialect="sqlite"),
)

# Hai trigger này tham chiếu vehicles/parking_sessions, nên chỉ cài sau khi
# toàn bộ metadata đã được tạo. Router trả 409 dễ hiểu; DB giữ bất biến cho
# race condition và các đường ghi ngoài API.
event.listen(
    Base.metadata,
    "after_create",
    DDL(PRICE_ACTIVE_SESSION_UPDATE_GUARD_TRIGGER_SQL).execute_if(
        dialect="sqlite"
    ),
)
event.listen(
    Base.metadata,
    "after_create",
    DDL(PRICE_ACTIVE_SESSION_DELETE_GUARD_TRIGGER_SQL).execute_if(
        dialect="sqlite"
    ),
)
event.listen(
    Base.metadata,
    "after_create",
    DDL(PRICE_ACTIVE_SESSION_REPLACE_GUARD_TRIGGER_SQL).execute_if(
        dialect="sqlite"
    ),
)
