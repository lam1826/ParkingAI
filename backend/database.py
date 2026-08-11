import os
from pathlib import Path
from sqlalchemy import create_engine
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
