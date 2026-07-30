from fastapi import APIRouter

# Import các router con
from routers import role, user, vehicle_type, zone, parking_slot, customer, vehicle
from routers import monthly_pass, price_config, parking_session
# Lưu ý: ai_report được mount trực tiếp ở main.py (đã có prefix "/ai" riêng),
# không include lại ở đây để tránh trùng prefix -> sai đường dẫn API.

# Khởi tạo Master Router
api_router = APIRouter()

# Đăng ký các router con vào Master Router
api_router.include_router(role.router, prefix="/roles", tags=["Roles"])
api_router.include_router(user.router, prefix="/users", tags=["Users"])
api_router.include_router(vehicle_type.router, prefix="/vehicle-types", tags=["Vehicle Types"])
api_router.include_router(zone.router, prefix="/zones", tags=["Zones"])
api_router.include_router(parking_slot.router, prefix="/parking-slots", tags=["Parking Slots"])
api_router.include_router(customer.router, prefix="/customers", tags=["Customers"])
api_router.include_router(vehicle.router, prefix="/vehicles", tags=["Vehicles"])
api_router.include_router(monthly_pass.router, prefix="/monthly-passes", tags=["Monthly Passes"])
api_router.include_router(price_config.router, prefix="/price-configs", tags=["Price Configs"])
api_router.include_router(parking_session.router, prefix="/parking-sessions", tags=["Parking Sessions"])


