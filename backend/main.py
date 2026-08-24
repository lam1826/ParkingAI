import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from routers import auth, dashboard, parking, ai_report, report

# Import cấu hình database và toàn bộ Models
from database import engine, run_sqlite_migrations
from models import Base

# Import router cho bảng Role
from routers.api import api_router
from core.config import settings
from middleware.audit import AuditLogMiddleware

# --- KHỞI TẠO APP & METADATA ---
app = FastAPI(
    title="Parking Management System API",
    description="Hệ thống quản lý bãi đỗ xe thông minh tích hợp AI Text-to-SQL.",
    version="1.0.0"
)

# --- CẤU HÌNH CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLogMiddleware)


# --- XỬ LÝ LỖI RÀNG BUỘC TOÀN VẸN (khóa ngoại/unique) ---
# SQLite đã bật PRAGMA foreign_keys (database.py) nên các thao tác xóa/sửa
# vi phạm ràng buộc sẽ ném IntegrityError -> trả 409 thay vì 500.
@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={
            "detail": (
                "Thao tác vi phạm ràng buộc dữ liệu: bản ghi đang được "
                "tham chiếu bởi dữ liệu khác hoặc bị trùng lặp."
            )
        },
    )

# --- KHỞI TẠO DATABASE ---
# Migration additive cho DB đã tồn tại (create_all không ALTER bảng cũ),
# sau đó tạo các bảng còn thiếu nếu là DB mới.
run_sqlite_migrations(engine)
Base.metadata.create_all(bind=engine)




# --- ĐĂNG KÝ CÁC ROUTERS ---
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(auth.oauth_router, prefix="/auth", tags=["Auth"])
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
