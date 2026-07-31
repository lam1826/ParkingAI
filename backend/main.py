import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, dashboard, parking, ai_report, report
from routers.zone import router as zone_router

# Import cấu hình database và toàn bộ Models
from database import engine
from models import Base

# Import router cho bảng Role
from routers.api import api_router

# --- KHỞI TẠO APP & METADATA ---
app = FastAPI(
    title="Parking Management System API",
    description="Hệ thống quản lý bãi đỗ xe thông minh tích hợp AI Text-to-SQL.",
    version="1.0.0"
)

# --- CẤU HÌNH CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- KHỞI TẠO DATABASE ---
# Lệnh này sẽ kiểm tra và tạo file SQLite cùng tất cả các bảng nếu chưa tồn tại
Base.metadata.create_all(bind=engine)




# --- ĐĂNG KÝ CÁC ROUTERS ---
app.include_router(zone_router, prefix="/zones", tags=["Zones"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(dashboard.router)
app.include_router(parking.router)
app.include_router(ai_report.router)
app.include_router(report.router)
app.include_router(api_router, prefix="/api/v1")




# --- ENDPOINTS CHÍNH ---
@app.get("/", tags=["Health Check"])
def home():
    return {
        "status": "success",
        "message": "Welcome to the Parking Management API!",
        "version": "1.0.0"
    }


# --- CHẠY SERVER BẰNG PYTHON ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)