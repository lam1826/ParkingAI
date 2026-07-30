# models/__init__.py

from database import Base

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
]