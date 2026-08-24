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


def run_sqlite_migrations(target_engine=engine) -> None:
    """Migration additive, idempotent cho database SQLite đã tồn tại.

    `Base.metadata.create_all()` chỉ tạo bảng MỚI, không ALTER bảng cũ — nên các
    cột thêm vào model sau này phải được bổ sung tại đây cho DB đã có sẵn.
    Chỉ dùng ALTER TABLE ADD COLUMN (thuần additive, không đụng dữ liệu cũ);
    an toàn khi chạy nhiều lần. DB mới tinh không cần: create_all tự tạo đủ schema.
    """
    if not str(target_engine.url).startswith("sqlite"):
        return
    with target_engine.begin() as conn:
        # --- monthly_passes: cột pass_code/price + unique index ---
        # Mỗi bảng xử lý độc lập: bảng chưa tồn tại thì bỏ qua (create_all sẽ
        # tạo đầy đủ theo model), không được return sớm làm mất phần bảng khác.
        columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(monthly_passes)")
        }
        if columns:
            if "pass_code" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE monthly_passes ADD COLUMN pass_code VARCHAR(50)"
                )
            if "price" not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE monthly_passes ADD COLUMN price INTEGER NOT NULL DEFAULT 0"
                )
            # Tên index phải khớp khai báo trong models/monthly_pass.py
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_monthly_passes_pass_code "
                "ON monthly_passes(pass_code) WHERE pass_code IS NOT NULL"
            )

        # --- price_configs: backstop một bảng giá active mỗi loại xe ---
        # Tên index phải khớp khai báo trong models/price_config.py.
        # Nếu DB cũ đang có sẵn hai bản ghi active cùng loại xe, lệnh này sẽ
        # ném IntegrityError khi khởi động: đó là tín hiệu cần dọn dữ liệu
        # trước, KHÔNG được im lặng bỏ qua vì bất biến đang bị vi phạm thật.
        price_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(price_configs)")
        }
        if price_columns:
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_price_config_one_active_per_vehicle_type "
                "ON price_configs(vehicle_type_id) WHERE is_active = 1"
            )

        # --- parking_sessions: backstop bất biến check-in (Đợt 3) ---
        # Tên index phải khớp khai báo trong models/parking_session.py.
        # Kiểm tra duplicate TRƯỚC khi tạo index để fail với thông báo đủ
        # thông tin cho quản trị viên dọn dữ liệu; tuyệt đối không tự xóa,
        # merge hay sửa bản ghi legacy.
        session_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(parking_sessions)")
        }
        if session_columns:
            dup_vehicles = conn.exec_driver_sql(
                "SELECT vehicle_id, COUNT(*) FROM parking_sessions"
                " WHERE status = 'active' GROUP BY vehicle_id HAVING COUNT(*) > 1"
            ).fetchall()
            dup_slots = conn.exec_driver_sql(
                "SELECT parking_slot_id, COUNT(*) FROM parking_sessions"
                " WHERE status = 'active' AND parking_slot_id IS NOT NULL"
                " GROUP BY parking_slot_id HAVING COUNT(*) > 1"
            ).fetchall()
            if dup_vehicles or dup_slots:
                raise RuntimeError(
                    "Không thể tạo unique index cho parking_sessions vì dữ liệu"
                    " hiện có đang vi phạm bất biến. Cần dọn thủ công trước:"
                    f" vehicle_id có nhiều phiên active = {dup_vehicles};"
                    f" parking_slot_id có nhiều phiên active = {dup_slots}."
                    " Hãy check-out hoặc đóng bớt các phiên trùng rồi khởi"
                    " động lại."
                )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_parking_session_one_active_per_vehicle "
                "ON parking_sessions(vehicle_id) WHERE status = 'active'"
            )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_parking_session_one_active_per_slot "
                "ON parking_sessions(parking_slot_id)"
                " WHERE status = 'active' AND parking_slot_id IS NOT NULL"
            )
