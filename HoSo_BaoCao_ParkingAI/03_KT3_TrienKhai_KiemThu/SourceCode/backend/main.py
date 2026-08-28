import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from routers import auth, dashboard, parking, ai_report, report

# Import cấu hình database và toàn bộ Models
# Import router cho bảng Role
from routers.api import api_router
from core.config import settings
from core.money import ExactVndRangeError
from core.errors import is_known_database_business_conflict
from database import engine
from db_rollout import check_database_readiness
from middleware.audit import AuditLogMiddleware

logger = logging.getLogger(__name__)
RELEASE_ID = os.getenv("RELEASE_ID", "development")

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


@app.exception_handler(ExactVndRangeError)
async def exact_vnd_range_error_handler(
    request: Request,
    exc: ExactVndRangeError,
):
    """Never serialize an inexact monetary aggregate as a JSON number."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


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


@app.exception_handler(DBAPIError)
async def database_error_handler(request: Request, exc: DBAPIError):
    """Map known PostgreSQL trigger conflicts; hide every raw DB diagnostic."""
    if is_known_database_business_conflict(exc):
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "Dữ liệu vừa thay đổi hoặc đang được sử dụng bởi thao tác "
                    "khác. Vui lòng tải lại và thử lại."
                )
            },
        )
    logger.error(
        "Unhandled database error on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Không thể truy cập cơ sở dữ liệu do lỗi hệ thống."},
    )

# --- DATABASE LIFECYCLE ---
# Import ASGI phải là thao tác read-only: không tự tạo bảng/migrate DB tại
# module scope. Trước khi khởi động một môi trường mới, quản trị viên chạy
# lệnh tường minh trong backend/db_rollout.py sau khi đã backup/preflight.




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
        "version": "1.0.0",
        "release_id": RELEASE_ID,
    }


@app.get("/ready", tags=["Health Check"])
def readiness():
    """Read-only database/schema readiness; liveness remains available at ``/``."""
    try:
        check_database_readiness(engine, deep=False)
    except Exception as exc:
        logger.warning("Database readiness failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "detail": "Database/schema chưa sẵn sàng",
            },
        )
    return {"status": "ready"}


# --- CHẠY SERVER BẰNG PYTHON ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
