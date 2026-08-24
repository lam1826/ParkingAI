import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Float, ForeignKey, DateTime, Index, text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

class ParkingSession(Base):
    __tablename__ = "parking_sessions"

    # Backstop ở tầng DB cho hai bất biến check-in (Đợt 3):
    # - Một phương tiện chỉ có tối đa MỘT phiên active.
    # - Một vị trí đỗ (non-null) chỉ có tối đa MỘT phiên active.
    # Partial index nên lịch sử phiên completed không bị giới hạn. Application
    # đã kiểm tra trước và trả 409; index này bắt race giữa hai request đồng
    # thời và các đường ghi ngoài API. Tên index phải khớp câu lệnh trong
    # database.py::run_sqlite_migrations.
    __table_args__ = (
        Index(
            "uq_parking_session_one_active_per_vehicle",
            "vehicle_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
        Index(
            "uq_parking_session_one_active_per_slot",
            "parking_slot_id",
            unique=True,
            sqlite_where=text("status = 'active' AND parking_slot_id IS NOT NULL"),
        ),
    )

    # Sử dụng UUID để tránh đoán mã vé. default sinh UUID tự động khi tạo bản ghi
    # mới (trước đây thiếu default nên insert sẽ ghi NULL vào cột khóa chính).
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    # Đổi tên slot_id -> parking_slot_id để khớp với các trường mà
    # services/parking_service.py và schemas/parking.py đang sử dụng.
    parking_slot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("parking_slots.id"))
    monthly_pass_id: Mapped[Optional[int]] = mapped_column(ForeignKey("monthly_passes.id"))

    # Đổi tên time_in/time_out -> check_in_time/check_out_time và fee -> parking_fee
    # để khớp với ParkingService.check_in/check_out và CheckOutResponse.
    check_in_time: Mapped[datetime] = mapped_column(DateTime)
    check_out_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    image_in_url: Mapped[Optional[str]] = mapped_column(String(255))
    image_out_url: Mapped[Optional[str]] = mapped_column(String(255))
    
    parking_fee: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))  # Trạng thái: 'active' (Đang trong bãi), 'completed' (Đã ra)
    
    staff_in_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    staff_out_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    # --- Các Quan hệ (Relationships) ---
    
    # Quan hệ N-1: Một lượt gửi xe thuộc về một phương tiện (định danh qua biển số)
    vehicle: Mapped["Vehicle"] = relationship(back_populates="parking_sessions")
    
    # Quan hệ N-1: Một lượt gửi xe chiếm dụng một vị trí đỗ (có thể Null nếu không xếp lốt)
    slot: Mapped[Optional["ParkingSlot"]] = relationship(back_populates="parking_sessions")
    
    # Quan hệ N-1: Một lượt gửi xe có thể sử dụng một vé tháng để xác thực (miễn phí lượt)
    monthly_pass: Mapped[Optional["MonthlyPass"]] = relationship(back_populates="parking_sessions")
    
    # Quan hệ N-1 (với User): Nhân viên thực hiện cho xe vào
    staff_in: Mapped["User"] = relationship(
        foreign_keys=[staff_in_id], back_populates="parking_sessions_in"
    )
    
    # Quan hệ N-1 (với User): Nhân viên thực hiện cho xe ra (có thể Null khi xe chưa ra)
    staff_out: Mapped[Optional["User"]] = relationship(
        foreign_keys=[staff_out_id], back_populates="parking_sessions_out"
    )