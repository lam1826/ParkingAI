import os
import sqlite3
import unicodedata
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
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
def _unicode_casefold(value):
    if value is None:
        return None
    return unicodedata.normalize("NFC", str(value).strip()).casefold()


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    # Gắn listener ở cấp Engine để cả engine production lẫn các engine riêng
    # trong test/scratch đều thực thi cùng ràng buộc. Kiểm tra connection thật
    # thay vì URL global để không gửi PRAGMA SQLite sang dialect khác.
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            "unicode_casefold",
            1,
            _unicode_casefold,
            deterministic=True,
        )
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

    `Base.metadata.create_all()` chỉ tạo bảng MỚI, không nâng schema cũ — nên
    cột, index và trigger thêm sau này phải được bổ sung tại đây cho DB đã có.
    Các bước đều idempotent và không tự sửa/xóa dữ liệu nghiệp vụ; dữ liệu
    legacy vi phạm bất biến sẽ làm startup fail với hướng dẫn dọn rõ ràng.
    DB mới tinh được `create_all()` tạo đầy đủ theo metadata/model.
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

        # --- zones / parking_slots: mã định danh không trùng sau chuẩn hóa ---
        # API trim tên và so sánh không phân biệt hoa/thường. Hai expression
        # index này là backstop cho race giữa các request và đường ghi ngoài
        # API. Dữ liệu legacy vi phạm phải được dọn thủ công; không tự đổi tên.
        zone_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(zones)")
        }
        if zone_columns:
            duplicate_zones = conn.exec_driver_sql(
                "SELECT unicode_casefold(name), group_concat(id), COUNT(*) "
                "FROM zones GROUP BY unicode_casefold(name) HAVING COUNT(*) > 1"
            ).fetchall()
            if duplicate_zones:
                raise RuntimeError(
                    "Không thể tạo unique index cho zones vì tên khu vực "
                    f"bị trùng sau chuẩn hóa: {duplicate_zones}. "
                    "Cần đổi tên thủ công rồi khởi động lại."
                )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_zones_name_normalized "
                "ON zones(unicode_casefold(name))"
            )

        slot_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(parking_slots)")
        }
        if slot_columns:
            duplicate_slots = conn.exec_driver_sql(
                "SELECT unicode_casefold(slot_name), group_concat(id), COUNT(*) "
                "FROM parking_slots GROUP BY unicode_casefold(slot_name) "
                "HAVING COUNT(*) > 1"
            ).fetchall()
            if duplicate_slots:
                raise RuntimeError(
                    "Không thể tạo unique index cho parking_slots vì mã vị "
                    f"trí bị trùng sau chuẩn hóa: {duplicate_slots}. "
                    "Cần đổi mã thủ công rồi khởi động lại."
                )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_parking_slots_name_normalized "
                "ON parking_slots(unicode_casefold(slot_name))"
            )

        if zone_columns and slot_columns:
            capacity_violations = conn.exec_driver_sql(
                "SELECT z.id, z.capacity, COUNT(ps.id) AS slot_count "
                "FROM zones AS z JOIN parking_slots AS ps ON ps.zone_id = z.id "
                "GROUP BY z.id, z.capacity HAVING COUNT(ps.id) > z.capacity"
            ).fetchall()
            if capacity_violations:
                raise RuntimeError(
                    "Không thể cài trigger sức chứa vì dữ liệu khu vực đang "
                    f"vượt sức chứa: {capacity_violations}. Cần tăng capacity "
                    "hoặc chuyển bớt vị trí rồi khởi động lại."
                )
            conn.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS "
                "trg_parking_slots_capacity_insert "
                "BEFORE INSERT ON parking_slots FOR EACH ROW "
                "WHEN (SELECT COUNT(*) FROM parking_slots "
                "WHERE zone_id = NEW.zone_id) >= "
                "COALESCE((SELECT capacity FROM zones "
                "WHERE id = NEW.zone_id), 0) "
                "BEGIN SELECT RAISE(ABORT, 'zone capacity exceeded'); END"
            )
            conn.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS "
                "trg_parking_slots_capacity_move "
                "BEFORE UPDATE OF zone_id ON parking_slots FOR EACH ROW "
                "WHEN NEW.zone_id != OLD.zone_id AND "
                "(SELECT COUNT(*) FROM parking_slots "
                "WHERE zone_id = NEW.zone_id) >= "
                "COALESCE((SELECT capacity FROM zones "
                "WHERE id = NEW.zone_id), 0) "
                "BEGIN SELECT RAISE(ABORT, 'zone capacity exceeded'); END"
            )
            conn.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS trg_zones_capacity_update "
                "BEFORE UPDATE OF capacity ON zones FOR EACH ROW "
                "WHEN NEW.capacity < (SELECT COUNT(*) FROM parking_slots "
                "WHERE zone_id = OLD.id) "
                "BEGIN SELECT RAISE(ABORT, "
                "'zone capacity below slot count'); END"
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
