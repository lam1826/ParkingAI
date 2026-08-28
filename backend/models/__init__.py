# models/__init__.py

from sqlalchemy import DDL, event

from database import Base, BOOLEAN_DOMAIN_TRIGGER_SQL

# Import toàn bộ các models tại đây để đăng ký với Base.metadata
from .role import Role
from .user import User
from .vehicle_type import VehicleType
from .zone import Zone
from .parking_slot import ParkingSlot
from .customer import Customer
from .vehicle import Vehicle
from .monthly_pass import MonthlyPass
from .price_config import PriceConfig
from .parking_session import ParkingSession
from .ai_report import AiReport
from .audit_log import AuditLog


# Cài canonical BOOLEAN backstop sau khi toàn bộ metadata đã tồn tại. Một
# registry dùng chung cũng cấp SQL cho migration/readiness, tránh lệch contract
# giữa DB mới và DB legacy.
for _boolean_trigger_sql in BOOLEAN_DOMAIN_TRIGGER_SQL.values():
    event.listen(
        Base.metadata,
        "after_create",
        DDL(_boolean_trigger_sql).execute_if(dialect="sqlite"),
    )

# Sử dụng __all__ để kiểm soát chính xác những gì được export ra 
# khi gọi `from models import *` và tránh cảnh báo unused import trong IDE
__all__ = [
    "Base",
    "Role",
    "User",
    "VehicleType",
    "Zone",
    "ParkingSlot",
    "Customer",
    "Vehicle",
    "MonthlyPass",
    "PriceConfig",
    "ParkingSession",
    "AiReport",
    "AuditLog",
]
