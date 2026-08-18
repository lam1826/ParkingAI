import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# 1. Định nghĩa đường dẫn tới file database SQLite
# ĐỔI TÊN THƯ MỤC: Đổi từ "./database" thành "./db_data" để tránh xung đột với tên file database.py
BACKEND_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BACKEND_DIR / "database"
DATABASE_FILE = DATABASE_DIR / "parking.db"
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{DATABASE_FILE.as_posix()}"
)

# Đảm bảo thư mục tồn tại trước khi tạo DB
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# 2. Tạo Engine
# check_same_thread=False là bắt buộc khi dùng SQLite với FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False  # Đặt thành True nếu bạn muốn log toàn bộ câu lệnh SQL ra console để debug
)


# SQLite mặc định KHÔNG thực thi ràng buộc khóa ngoại -> bật cho mọi connection
# để đảm bảo toàn vẹn dữ liệu (zone/slot/vehicle_type... không bị bản ghi mồ côi).
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# 3. Tạo SessionLocal
# Đây là factory để tạo ra các session (phiên làm việc) với CSDL cho mỗi request
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine
)

# 4. Khởi tạo Base class (Chuẩn SQLAlchemy 2.x)
# Các Model của bạn sẽ kế thừa từ class này
class Base(DeclarativeBase):
    pass

# Hàm helper (Dependency) để inject database session vào các route của FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
