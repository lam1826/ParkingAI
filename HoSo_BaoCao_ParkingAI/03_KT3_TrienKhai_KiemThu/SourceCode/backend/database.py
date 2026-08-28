import os
import sqlite3
import unicodedata
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.money import MAX_EXACT_VND

# 1. Định nghĩa đường dẫn tới file database SQLite
# ĐỔI TÊN THƯ MỤC: Đổi từ "./database" thành "./db_data" để tránh xung đột với tên file database.py
BACKEND_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BACKEND_DIR / "database"
DATABASE_FILE = DATABASE_DIR / "parking.db"
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{DATABASE_FILE.as_posix()}"
)

# Không tạo thư mục/file ở module scope: import ASGI và readiness phải hoàn
# toàn read-only. `db_rollout.initialize_database()` chịu trách nhiệm tạo thư
# mục đích khi quản trị viên chạy migration tường minh.

def create_database_engine(database_url: str):
    """Build the SQLAlchemy adapter without leaking dialect options.

    SQLite needs ``check_same_thread=False`` for FastAPI. PostgreSQL rejects
    that argument, and benefits from pre-ping so a managed database failover
    does not leave stale pooled connections in a long-running container.
    """
    if database_url.startswith("postgresql://"):
        # SQLAlchemy otherwise defaults to the psycopg2 driver, while this
        # project deliberately ships psycopg 3 only.
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    options = {"echo": False, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    elif database_url.startswith("postgresql+psycopg://"):
        try:
            pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
            max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "5"))
            pool_recycle = int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800"))
        except ValueError as exc:
            raise RuntimeError("PostgreSQL pool settings must be integers") from exc
        if pool_size < 1 or max_overflow < 0 or pool_recycle < 1:
            raise RuntimeError("PostgreSQL pool settings are outside safe bounds")
        options.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
        )
    return create_engine(database_url, **options)


# 2. Tạo Engine
engine = create_database_engine(SQLALCHEMY_DATABASE_URL)


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
        # SQLite chỉ chạy DELETE trigger do INSERT OR REPLACE gây ra khi
        # recursive_triggers bật. Nếu để mặc định OFF, một câu REPLACE có thể
        # lách guard khóa bảng giá của phiên đang mở bằng cách xóa ngầm row cũ.
        cursor.execute("PRAGMA recursive_triggers=ON")
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


# SQLite khai báo BOOLEAN chỉ là type affinity và vẫn chấp nhận 2/-1/text.
# Toàn bộ code nghiệp vụ so sánh canonical 0/1, vì vậy mọi cột bool phải có
# backstop đồng nhất cho API, script ngoài và dữ liệu legacy.
BOOLEAN_DOMAIN_COLUMNS = {
    "users": ("is_active",),
    "vehicle_types": ("is_active",),
    "zones": ("is_active",),
    "parking_slots": ("is_occupied", "is_active"),
    "monthly_passes": ("is_active",),
    "price_configs": ("is_active",),
    "audit_logs": ("success",),
}


def _boolean_domain_trigger_sql(table_name: str, columns: tuple[str, ...]):
    invalid_new = " OR ".join(
        f"NEW.{column} IS NULL OR typeof(NEW.{column}) != 'integer' "
        f"OR NEW.{column} NOT IN (0, 1)"
        for column in columns
    )
    update_columns = ", ".join(columns)
    insert_name = f"trg_{table_name}_boolean_domain_insert"
    update_name = f"trg_{table_name}_boolean_domain_update"
    return {
        insert_name: (
            f"CREATE TRIGGER IF NOT EXISTS {insert_name} "
            f"BEFORE INSERT ON {table_name} FOR EACH ROW WHEN {invalid_new} "
            "BEGIN SELECT RAISE(ABORT, 'boolean value must be 0 or 1'); END"
        ),
        update_name: (
            f"CREATE TRIGGER IF NOT EXISTS {update_name} "
            f"BEFORE UPDATE OF {update_columns} ON {table_name} FOR EACH ROW "
            f"WHEN {invalid_new} "
            "BEGIN SELECT RAISE(ABORT, 'boolean value must be 0 or 1'); END"
        ),
    }


BOOLEAN_DOMAIN_TRIGGER_SQL = {
    trigger_name: trigger_sql
    for table_name, columns in BOOLEAN_DOMAIN_COLUMNS.items()
    for trigger_name, trigger_sql in _boolean_domain_trigger_sql(
        table_name, columns
    ).items()
}


TRG_VEHICLE_TYPE_IMMUTABLE_WITH_HISTORY = (
    "trg_vehicles_vehicle_type_immutable_with_history"
)
VEHICLE_TYPE_IMMUTABLE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_VEHICLE_TYPE_IMMUTABLE_WITH_HISTORY} "
    "BEFORE UPDATE OF vehicle_type_id ON vehicles FOR EACH ROW "
    "WHEN NEW.vehicle_type_id != OLD.vehicle_type_id AND ("
    "EXISTS (SELECT 1 FROM parking_sessions WHERE vehicle_id = OLD.id) "
    "OR EXISTS (SELECT 1 FROM monthly_passes WHERE vehicle_id = OLD.id)) "
    "BEGIN SELECT RAISE(ABORT, "
    "'vehicle type immutable after history'); END"
)

TRG_VEHICLE_LICENSE_PLATE_IMMUTABLE_WITH_HISTORY = (
    "trg_vehicles_license_plate_immutable_with_history"
)
VEHICLE_LICENSE_PLATE_IMMUTABLE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS "
    f"{TRG_VEHICLE_LICENSE_PLATE_IMMUTABLE_WITH_HISTORY} "
    "BEFORE UPDATE OF license_plate ON vehicles FOR EACH ROW "
    "WHEN NEW.license_plate IS NOT OLD.license_plate AND EXISTS ("
    "SELECT 1 FROM parking_sessions WHERE vehicle_id = OLD.id) "
    "BEGIN SELECT RAISE(ABORT, "
    "'license plate immutable after history'); END"
)

TRG_MONTHLY_PASS_HISTORY_IMMUTABLE = (
    "trg_monthly_passes_history_immutable"
)
MONTHLY_PASS_HISTORY_IMMUTABLE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_MONTHLY_PASS_HISTORY_IMMUTABLE} "
    "BEFORE UPDATE OF customer_id, vehicle_id, pass_code, price, "
    "start_date, end_date ON monthly_passes FOR EACH ROW "
    "WHEN EXISTS (SELECT 1 FROM parking_sessions "
    "WHERE monthly_pass_id = OLD.id) AND ("
    "NEW.customer_id IS NOT OLD.customer_id "
    "OR NEW.vehicle_id IS NOT OLD.vehicle_id "
    "OR NEW.pass_code IS NOT OLD.pass_code "
    "OR NEW.price IS NOT OLD.price "
    "OR NEW.start_date IS NOT OLD.start_date "
    "OR NEW.end_date IS NOT OLD.end_date) "
    "BEGIN SELECT RAISE(ABORT, 'monthly pass history immutable'); END"
)

TRG_MONTHLY_PASS_PRICE_INSERT = "trg_monthly_passes_integer_price_insert"
TRG_MONTHLY_PASS_PRICE_UPDATE = "trg_monthly_passes_integer_price_update"
MONTHLY_PASS_PRICE_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_MONTHLY_PASS_PRICE_INSERT} "
    "BEFORE INSERT ON monthly_passes FOR EACH ROW "
    "WHEN NEW.price IS NULL OR NEW.price < 0 "
    "OR NEW.price != CAST(NEW.price AS INTEGER) "
    f"OR NEW.price > {MAX_EXACT_VND} "
    "BEGIN SELECT RAISE(ABORT, "
    "'monthly pass price must be nonnegative integer'); END"
)
MONTHLY_PASS_PRICE_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_MONTHLY_PASS_PRICE_UPDATE} "
    "BEFORE UPDATE OF price ON monthly_passes FOR EACH ROW "
    "WHEN NEW.price IS NULL OR NEW.price < 0 "
    "OR NEW.price != CAST(NEW.price AS INTEGER) "
    f"OR NEW.price > {MAX_EXACT_VND} "
    "BEGIN SELECT RAISE(ABORT, "
    "'monthly pass price must be nonnegative integer'); END"
)

TRG_MONTHLY_PASS_DATE_RANGE_INSERT = "trg_monthly_passes_date_range_insert"
TRG_MONTHLY_PASS_DATE_RANGE_UPDATE = "trg_monthly_passes_date_range_update"
MONTHLY_PASS_DATE_RANGE_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_MONTHLY_PASS_DATE_RANGE_INSERT} "
    "BEFORE INSERT ON monthly_passes FOR EACH ROW "
    "WHEN NEW.start_date IS NULL OR NEW.end_date IS NULL "
    "OR typeof(NEW.start_date) != 'text' "
    "OR typeof(NEW.end_date) != 'text' "
    "OR NEW.start_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "OR NEW.end_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "OR substr(NEW.start_date, 1, 4) = '0000' "
    "OR substr(NEW.end_date, 1, 4) = '0000' "
    "OR date(NEW.start_date, '+0 days') IS NULL "
    "OR date(NEW.end_date, '+0 days') IS NULL "
    "OR date(NEW.start_date, '+0 days') != NEW.start_date "
    "OR date(NEW.end_date, '+0 days') != NEW.end_date "
    "OR NEW.end_date < NEW.start_date "
    "BEGIN SELECT RAISE(ABORT, 'monthly pass date range invalid'); END"
)
MONTHLY_PASS_DATE_RANGE_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_MONTHLY_PASS_DATE_RANGE_UPDATE} "
    "BEFORE UPDATE OF start_date, end_date ON monthly_passes FOR EACH ROW "
    "WHEN NEW.start_date IS NULL OR NEW.end_date IS NULL "
    "OR typeof(NEW.start_date) != 'text' "
    "OR typeof(NEW.end_date) != 'text' "
    "OR NEW.start_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "OR NEW.end_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "OR substr(NEW.start_date, 1, 4) = '0000' "
    "OR substr(NEW.end_date, 1, 4) = '0000' "
    "OR date(NEW.start_date, '+0 days') IS NULL "
    "OR date(NEW.end_date, '+0 days') IS NULL "
    "OR date(NEW.start_date, '+0 days') != NEW.start_date "
    "OR date(NEW.end_date, '+0 days') != NEW.end_date "
    "OR NEW.end_date < NEW.start_date "
    "BEGIN SELECT RAISE(ABORT, 'monthly pass date range invalid'); END"
)

TRG_PRICE_INTEGER_INSERT = "trg_price_configs_integer_price_insert"
TRG_PRICE_INTEGER_UPDATE = "trg_price_configs_integer_price_update"
PRICE_INTEGER_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_INTEGER_INSERT} "
    "BEFORE INSERT ON price_configs FOR EACH ROW "
    "WHEN NEW.price IS NULL OR NEW.price < 0 "
    "OR NEW.price != CAST(NEW.price AS INTEGER) "
    "BEGIN SELECT RAISE(ABORT, "
    "'price must be nonnegative integer'); END"
)
PRICE_INTEGER_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_INTEGER_UPDATE} "
    "BEFORE UPDATE OF price ON price_configs FOR EACH ROW "
    "WHEN NEW.price IS NULL OR NEW.price < 0 "
    "OR NEW.price != CAST(NEW.price AS INTEGER) "
    "BEGIN SELECT RAISE(ABORT, "
    "'price must be nonnegative integer'); END"
)

TRG_PRICE_TICKET_TYPE_INSERT = "trg_price_configs_ticket_type_insert"
TRG_PRICE_TICKET_TYPE_UPDATE = "trg_price_configs_ticket_type_update"
PRICE_TICKET_TYPE_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_TICKET_TYPE_INSERT} "
    "BEFORE INSERT ON price_configs FOR EACH ROW "
    "WHEN NEW.ticket_type IS NULL "
    "OR NEW.ticket_type NOT IN ('HOURLY', 'DAILY') "
    "BEGIN SELECT RAISE(ABORT, "
    "'ticket type must be HOURLY or DAILY'); END"
)
PRICE_TICKET_TYPE_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_TICKET_TYPE_UPDATE} "
    "BEFORE UPDATE OF ticket_type ON price_configs FOR EACH ROW "
    "WHEN NEW.ticket_type IS NULL "
    "OR NEW.ticket_type NOT IN ('HOURLY', 'DAILY') "
    "BEGIN SELECT RAISE(ABORT, "
    "'ticket type must be HOURLY or DAILY'); END"
)

TRG_PRICE_EFFECTIVE_DATE_INSERT = "trg_price_configs_effective_date_insert"
TRG_PRICE_EFFECTIVE_DATE_UPDATE = "trg_price_configs_effective_date_update"
PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_EFFECTIVE_DATE_INSERT} "
    "BEFORE INSERT ON price_configs FOR EACH ROW "
    "WHEN NEW.effective_date IS NULL "
    "OR typeof(NEW.effective_date) != 'text' "
    "OR NEW.effective_date NOT GLOB "
    "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "OR substr(NEW.effective_date, 1, 4) = '0000' "
    "OR date(NEW.effective_date, '+0 days') IS NULL "
    "OR date(NEW.effective_date, '+0 days') != NEW.effective_date "
    "BEGIN SELECT RAISE(ABORT, 'price effective date invalid'); END"
)
PRICE_EFFECTIVE_DATE_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_EFFECTIVE_DATE_UPDATE} "
    "BEFORE UPDATE OF effective_date ON price_configs FOR EACH ROW "
    "WHEN NEW.effective_date IS NULL "
    "OR typeof(NEW.effective_date) != 'text' "
    "OR NEW.effective_date NOT GLOB "
    "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
    "OR substr(NEW.effective_date, 1, 4) = '0000' "
    "OR date(NEW.effective_date, '+0 days') IS NULL "
    "OR date(NEW.effective_date, '+0 days') != NEW.effective_date "
    "BEGIN SELECT RAISE(ABORT, 'price effective date invalid'); END"
)

TRG_PRICE_ACTIVE_SESSION_UPDATE_GUARD = (
    "trg_price_configs_active_session_update_guard_v2"
)
PRICE_ACTIVE_SESSION_UPDATE_GUARD_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_ACTIVE_SESSION_UPDATE_GUARD} "
    "BEFORE UPDATE OF vehicle_type_id, ticket_type, price, effective_date, "
    "is_active ON price_configs FOR EACH ROW "
    "WHEN OLD.is_active = 1 AND ("
    "NEW.vehicle_type_id IS NOT OLD.vehicle_type_id "
    "OR NEW.ticket_type IS NOT OLD.ticket_type "
    "OR NEW.price IS NOT OLD.price "
    "OR NEW.effective_date IS NOT OLD.effective_date "
    "OR NEW.is_active IS NOT OLD.is_active) AND EXISTS ("
    "SELECT 1 FROM parking_sessions AS ps "
    "JOIN vehicles AS v ON v.id = ps.vehicle_id "
    "WHERE ps.status = 'active' "
    "AND v.vehicle_type_id = OLD.vehicle_type_id) "
    "BEGIN SELECT RAISE(ABORT, 'active parking session uses price config'); END"
)

TRG_PRICE_ACTIVE_SESSION_DELETE_GUARD = (
    "trg_price_configs_active_session_delete_guard_v2"
)
PRICE_ACTIVE_SESSION_DELETE_GUARD_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_ACTIVE_SESSION_DELETE_GUARD} "
    "BEFORE DELETE ON price_configs FOR EACH ROW "
    "WHEN OLD.is_active = 1 AND EXISTS ("
    "SELECT 1 FROM parking_sessions AS ps "
    "JOIN vehicles AS v ON v.id = ps.vehicle_id "
    "WHERE ps.status = 'active' "
    "AND v.vehicle_type_id = OLD.vehicle_type_id) "
    "BEGIN SELECT RAISE(ABORT, 'active parking session uses price config'); END"
)

TRG_PRICE_ACTIVE_SESSION_REPLACE_GUARD = (
    "trg_price_configs_active_session_replace_guard"
)
PRICE_ACTIVE_SESSION_REPLACE_GUARD_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_ACTIVE_SESSION_REPLACE_GUARD} "
    "BEFORE INSERT ON price_configs FOR EACH ROW WHEN EXISTS ("
    "SELECT 1 FROM price_configs AS existing "
    "JOIN vehicles AS v "
    "ON v.vehicle_type_id = existing.vehicle_type_id "
    "JOIN parking_sessions AS ps ON ps.vehicle_id = v.id "
    "WHERE existing.is_active = 1 AND ps.status = 'active' "
    "AND (existing.id = NEW.id OR (NEW.is_active = 1 "
    "AND existing.vehicle_type_id = NEW.vehicle_type_id))) "
    "BEGIN SELECT RAISE(ABORT, 'active parking session uses price config'); END"
)

def _sqlite_fee_domain_invalid(column_sql: str) -> str:
    """Predicate OWNED by the parking_fee money triggers.

    SQLite does not guarantee the firing order of several BEFORE triggers on
    one statement, so overlapping WHEN clauses would make the abort message
    non-deterministic.  Money-domain violations are the highest precedence
    contract for ``parking_sessions.parking_fee``; every other trigger that
    could also match such a row subtracts this predicate instead of racing
    for the message.  The union of the two fee triggers below is exactly this
    expression, so nothing escapes validation.
    """
    return (
        f"{column_sql} IS NOT NULL AND ({column_sql} < 0 "
        f"OR {column_sql} != CAST({column_sql} AS INTEGER) "
        f"OR {column_sql} > {MAX_EXACT_VND})"
    )


TRG_PARKING_FEE_INTEGER_INSERT = "trg_parking_sessions_integer_fee_insert"
TRG_PARKING_FEE_INTEGER_UPDATE = "trg_parking_sessions_integer_fee_update"
PARKING_FEE_INTEGER_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PARKING_FEE_INTEGER_INSERT} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    "WHEN NEW.parking_fee IS NOT NULL AND (NEW.parking_fee < 0 "
    "OR NEW.parking_fee != CAST(NEW.parking_fee AS INTEGER)) "
    "BEGIN SELECT RAISE(ABORT, "
    "'parking fee must be nonnegative integer'); END"
)
PARKING_FEE_INTEGER_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PARKING_FEE_INTEGER_UPDATE} "
    "BEFORE UPDATE OF parking_fee ON parking_sessions FOR EACH ROW "
    "WHEN NEW.parking_fee IS NOT NULL AND (NEW.parking_fee < 0 "
    "OR NEW.parking_fee != CAST(NEW.parking_fee AS INTEGER)) "
    "BEGIN SELECT RAISE(ABORT, "
    "'parking fee must be nonnegative integer'); END"
)

TRG_PRICE_SAFE_VND_INSERT = "trg_price_configs_safe_vnd_insert"
TRG_PRICE_SAFE_VND_UPDATE = "trg_price_configs_safe_vnd_update"
PRICE_SAFE_VND_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_SAFE_VND_INSERT} "
    "BEFORE INSERT ON price_configs FOR EACH ROW "
    f"WHEN NEW.price > {MAX_EXACT_VND} "
    "BEGIN SELECT RAISE(ABORT, 'price exceeds exact VND range'); END"
)
PRICE_SAFE_VND_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PRICE_SAFE_VND_UPDATE} "
    "BEFORE UPDATE OF price ON price_configs FOR EACH ROW "
    f"WHEN NEW.price > {MAX_EXACT_VND} "
    "BEGIN SELECT RAISE(ABORT, 'price exceeds exact VND range'); END"
)
TRG_PARKING_FEE_SAFE_VND_INSERT = "trg_parking_sessions_safe_vnd_insert"
TRG_PARKING_FEE_SAFE_VND_UPDATE = "trg_parking_sessions_safe_vnd_update"
# Range chỉ phán xét giá trị ĐÃ qua domain số nguyên không âm; nếu không, một
# REAL khổng lồ (vừa không nguyên vừa vượt range) khớp cả hai trigger và thông
# báo phụ thuộc thứ tự trigger — thứ tự mà SQLite không đảm bảo.
_PARKING_FEE_ABOVE_EXACT_VND = (
    "NEW.parking_fee IS NOT NULL AND NEW.parking_fee >= 0 "
    "AND NEW.parking_fee = CAST(NEW.parking_fee AS INTEGER) "
    f"AND NEW.parking_fee > {MAX_EXACT_VND}"
)
PARKING_FEE_SAFE_VND_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PARKING_FEE_SAFE_VND_INSERT} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    f"WHEN {_PARKING_FEE_ABOVE_EXACT_VND} "
    "BEGIN SELECT RAISE(ABORT, 'parking fee exceeds exact VND range'); END"
)
PARKING_FEE_SAFE_VND_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PARKING_FEE_SAFE_VND_UPDATE} "
    "BEFORE UPDATE OF parking_fee ON parking_sessions FOR EACH ROW "
    f"WHEN {_PARKING_FEE_ABOVE_EXACT_VND} "
    "BEGIN SELECT RAISE(ABORT, 'parking fee exceeds exact VND range'); END"
)

TRG_SESSION_MONTHLY_PASS_INSERT_VALIDATION = (
    "trg_parking_sessions_monthly_pass_insert_validation"
)
SESSION_MONTHLY_PASS_INSERT_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS "
    f"{TRG_SESSION_MONTHLY_PASS_INSERT_VALIDATION} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    "WHEN NEW.monthly_pass_id IS NOT NULL AND NOT EXISTS ("
    "SELECT 1 FROM monthly_passes "
    "WHERE id = NEW.monthly_pass_id "
    "AND vehicle_id = NEW.vehicle_id "
    "AND is_active = 1 "
    "AND start_date <= date(NEW.check_in_time) "
    "AND end_date >= date(NEW.check_in_time)) "
    "BEGIN SELECT RAISE(ABORT, "
    "'monthly pass is not eligible at check-in'); END"
)

TRG_SESSION_RATE_INSERT_VALIDATION = (
    "trg_parking_sessions_rate_insert_validation_v2"
)
SESSION_RATE_INSERT_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_RATE_INSERT_VALIDATION} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    "WHEN NEW.status = 'active' AND NOT EXISTS ("
    "SELECT 1 FROM price_configs AS pc "
    "JOIN vehicles AS v ON v.vehicle_type_id = pc.vehicle_type_id "
    "WHERE v.id = NEW.vehicle_id "
    "AND pc.is_active = 1 "
    "AND pc.effective_date <= date(NEW.check_in_time)) "
    "BEGIN SELECT RAISE(ABORT, "
    "'active parking session requires effective price config'); END"
)

TRG_SESSION_RATE_ACTIVATION_VALIDATION = (
    "trg_parking_sessions_rate_activation_validation"
)
SESSION_RATE_ACTIVATION_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_RATE_ACTIVATION_VALIDATION} "
    "BEFORE UPDATE OF status ON parking_sessions FOR EACH ROW "
    "WHEN NEW.status = 'active' AND OLD.status IS NOT 'active' "
    # Hồi sinh phiên completed thuộc quyền của trigger terminal; không tranh
    # thông báo với nó (thứ tự trigger SQLite không xác định).
    "AND OLD.status IS NOT 'completed' "
    "AND NOT EXISTS ("
    "SELECT 1 FROM price_configs AS pc "
    "JOIN vehicles AS v ON v.vehicle_type_id = pc.vehicle_type_id "
    "WHERE v.id = NEW.vehicle_id "
    "AND pc.is_active = 1 "
    "AND pc.effective_date <= date(NEW.check_in_time)) "
    "BEGIN SELECT RAISE(ABORT, "
    "'active parking session requires effective price config'); END"
)

TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION = (
    "trg_parking_sessions_slot_admission_insert_validation"
)
SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS "
    f"{TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    "WHEN NEW.status = 'active' AND NEW.parking_slot_id IS NOT NULL "
    "AND NOT EXISTS ("
    "SELECT 1 FROM parking_slots AS ps "
    "JOIN zones AS z ON z.id = ps.zone_id "
    "JOIN vehicles AS v ON v.id = NEW.vehicle_id "
    "WHERE ps.id = NEW.parking_slot_id "
    "AND ps.vehicle_type_id = v.vehicle_type_id "
    "AND ps.is_active = 1 AND z.is_active = 1) "
    "BEGIN SELECT RAISE(ABORT, "
    "'parking slot is not eligible for active session'); END"
)

TRG_SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION = (
    "trg_parking_sessions_slot_admission_activation_validation"
)
SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS "
    f"{TRG_SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION} "
    "BEFORE UPDATE OF status ON parking_sessions FOR EACH ROW "
    "WHEN NEW.status = 'active' AND OLD.status IS NOT 'active' "
    "AND OLD.status IS NOT 'completed' "
    "AND NEW.parking_slot_id IS NOT NULL AND NOT EXISTS ("
    "SELECT 1 FROM parking_slots AS ps "
    "JOIN zones AS z ON z.id = ps.zone_id "
    "JOIN vehicles AS v ON v.id = NEW.vehicle_id "
    "WHERE ps.id = NEW.parking_slot_id "
    "AND ps.vehicle_type_id = v.vehicle_type_id "
    "AND ps.is_active = 1 AND z.is_active = 1) "
    "BEGIN SELECT RAISE(ABORT, "
    "'parking slot is not eligible for active session'); END"
)


def _sqlite_datetime_invalid(column_sql: str) -> str:
    """SQL predicate for SQLAlchemy's canonical naive SQLite DateTime text."""
    return (
        f"{column_sql} IS NULL OR typeof({column_sql}) != 'text' "
        f"OR length({column_sql}) < 19 OR length({column_sql}) > 26 "
        f"OR substr({column_sql}, 1, 4) = '0000' "
        f"OR {column_sql} NOT GLOB "
        "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] "
        "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]*' "
        f"OR (length({column_sql}) > 19 AND ("
        f"substr({column_sql}, 20, 1) != '.' "
        f"OR length({column_sql}) = 20 "
        f"OR substr({column_sql}, 21) GLOB '*[^0-9]*')) "
        f"OR datetime(substr({column_sql}, 1, 19), '+0 seconds') IS NULL "
        f"OR datetime(substr({column_sql}, 1, 19), '+0 seconds') "
        f"!= substr({column_sql}, 1, 19)"
    )


TRG_SESSION_STATUS_INSERT_VALIDATION = (
    "trg_parking_sessions_status_insert_validation"
)
TRG_SESSION_STATUS_UPDATE_VALIDATION = (
    "trg_parking_sessions_status_update_validation"
)
SESSION_STATUS_INSERT_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_STATUS_INSERT_VALIDATION} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    "WHEN NEW.status IS NULL "
    "OR NEW.status NOT IN ('active', 'completed', 'cancelled') "
    "BEGIN SELECT RAISE(ABORT, 'parking session status invalid'); END"
)
SESSION_STATUS_UPDATE_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_STATUS_UPDATE_VALIDATION} "
    "BEFORE UPDATE OF status ON parking_sessions FOR EACH ROW "
    # Mọi UPDATE trên hàng completed thuộc quyền của terminal/billing/identity
    # trigger; trigger này không tranh thông báo với chúng.
    "WHEN OLD.status IS NOT 'completed' AND ("
    "NEW.status IS NULL OR NEW.status NOT IN "
    "('active', 'checking_out', 'completed', 'cancelled') "
    "OR (NEW.status = 'checking_out' AND OLD.status != 'active') "
    "OR (OLD.status = 'checking_out' AND NEW.status != 'completed')) "
    "BEGIN SELECT RAISE(ABORT, 'parking session status invalid'); END"
)

TRG_SESSION_DATETIME_INSERT_VALIDATION = (
    "trg_parking_sessions_datetime_insert_validation"
)
TRG_SESSION_DATETIME_UPDATE_VALIDATION = (
    "trg_parking_sessions_datetime_update_validation"
)
SESSION_DATETIME_INSERT_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_DATETIME_INSERT_VALIDATION} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW WHEN ("
    f"{_sqlite_datetime_invalid('NEW.check_in_time')}) "
    "OR (NEW.check_out_time IS NOT NULL AND ("
    f"{_sqlite_datetime_invalid('NEW.check_out_time')})) "
    "BEGIN SELECT RAISE(ABORT, 'parking session datetime invalid'); END"
)
SESSION_DATETIME_UPDATE_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_DATETIME_UPDATE_VALIDATION} "
    "BEFORE UPDATE OF check_in_time, check_out_time ON parking_sessions "
    "FOR EACH ROW WHEN ("
    f"{_sqlite_datetime_invalid('NEW.check_in_time')}) "
    "OR (NEW.check_out_time IS NOT NULL AND ("
    f"{_sqlite_datetime_invalid('NEW.check_out_time')})) "
    "BEGIN SELECT RAISE(ABORT, 'parking session datetime invalid'); END"
)

TRG_SESSION_STATE_INSERT_VALIDATION = (
    "trg_parking_sessions_state_insert_validation"
)
TRG_SESSION_STATE_UPDATE_VALIDATION = (
    "trg_parking_sessions_state_update_validation"
)
_SESSION_STATE_INVALID_NEW = (
    "(NEW.status = 'completed' AND (NEW.check_out_time IS NULL "
    "OR NEW.parking_fee IS NULL OR NEW.staff_out_id IS NULL "
    "OR NEW.check_out_time < NEW.check_in_time)) "
    "OR (NEW.status IN ('active', 'checking_out') AND ("
    "NEW.check_out_time IS NOT NULL OR NEW.parking_fee IS NOT NULL "
    "OR NEW.staff_out_id IS NOT NULL))"
)
# Thứ tự ưu tiên xác định (SQLite KHÔNG đảm bảo thứ tự nổ giữa nhiều BEFORE
# trigger, nên các WHEN phải rời nhau thay vì dựa vào thứ tự tạo):
#   1. domain tiền  -> trg_parking_sessions_integer_fee_* / _safe_vnd_*
#   2. phiên completed -> trg_..._completed_status_terminal /
#                          trg_..._completed_billing_immutable
#   3. state đầy đủ  -> trigger dưới đây
# Trừ đi hai nhóm trên KHÔNG nới lỏng gì: mọi hàng bị trừ vẫn bị chính trigger
# sở hữu nó ABORT, chỉ khác thông báo trở nên xác định.
#
# Nhánh UPDATE chỉ trừ khi chính câu lệnh này đưa giá trị tiền sai vào: NEW
# khác OLD ở cột nào thì cột đó chắc chắn nằm trong SET list, nên trigger tiền
# (BEFORE UPDATE OF parking_fee) chắc chắn cùng nổ trên câu lệnh đó.
SESSION_STATE_INSERT_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_STATE_INSERT_VALIDATION} "
    "BEFORE INSERT ON parking_sessions FOR EACH ROW "
    f"WHEN ({_SESSION_STATE_INVALID_NEW}) "
    f"AND NOT ({_sqlite_fee_domain_invalid('NEW.parking_fee')}) "
    "BEGIN SELECT RAISE(ABORT, 'parking session state incomplete'); END"
)
SESSION_STATE_UPDATE_VALIDATION_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_STATE_UPDATE_VALIDATION} "
    "BEFORE UPDATE OF status, check_out_time, parking_fee, staff_out_id "
    "ON parking_sessions FOR EACH ROW "
    f"WHEN ({_SESSION_STATE_INVALID_NEW}) "
    f"AND NOT (({_sqlite_fee_domain_invalid('NEW.parking_fee')}) "
    f"AND NOT ({_sqlite_fee_domain_invalid('OLD.parking_fee')})) "
    "AND OLD.status IS NOT 'completed' "
    "BEGIN SELECT RAISE(ABORT, 'parking session state incomplete'); END"
)

# Cột parking_sessions bắt buộc phải có thì mới đánh giá/cài được contract
# vòng đời. DB legacy thiếu cột sẽ bị BỎ QUA ở migration (không thể query cột
# không tồn tại) chứ không bị sửa lén; verify_schema/`GET /ready` vẫn đòi đủ
# trigger nên một DB như vậy fail readiness rõ ràng thay vì chạy thiếu backstop.
SESSION_LIFECYCLE_COLUMNS = frozenset({
    "status",
    "parking_fee",
    "check_in_time",
    "check_out_time",
    "staff_in_id",
    "staff_out_id",
    "monthly_pass_id",
    "vehicle_id",
    "parking_slot_id",
})

TRG_SESSION_IDENTITY_IMMUTABLE = "trg_parking_sessions_identity_immutable"
SESSION_IDENTITY_IMMUTABLE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_IDENTITY_IMMUTABLE} "
    "BEFORE UPDATE OF vehicle_id, parking_slot_id, monthly_pass_id, "
    "check_in_time, staff_in_id ON parking_sessions FOR EACH ROW "
    "WHEN NEW.vehicle_id IS NOT OLD.vehicle_id "
    "OR NEW.parking_slot_id IS NOT OLD.parking_slot_id "
    "OR NEW.monthly_pass_id IS NOT OLD.monthly_pass_id "
    "OR NEW.check_in_time IS NOT OLD.check_in_time "
    "OR NEW.staff_in_id IS NOT OLD.staff_in_id "
    "BEGIN SELECT RAISE(ABORT, 'parking session identity is immutable'); END"
)

TRG_SESSION_COMPLETED_STATUS_TERMINAL = (
    "trg_parking_sessions_completed_status_terminal"
)
SESSION_COMPLETED_STATUS_TERMINAL_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_SESSION_COMPLETED_STATUS_TERMINAL} "
    "BEFORE UPDATE OF status ON parking_sessions FOR EACH ROW "
    "WHEN OLD.status = 'completed' AND NEW.status IS NOT OLD.status "
    "BEGIN SELECT RAISE(ABORT, 'completed parking session is terminal'); END"
)

TRG_SESSION_COMPLETED_BILLING_IMMUTABLE = (
    "trg_parking_sessions_completed_billing_immutable"
)
SESSION_COMPLETED_BILLING_IMMUTABLE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS "
    f"{TRG_SESSION_COMPLETED_BILLING_IMMUTABLE} "
    "BEFORE UPDATE OF check_out_time, parking_fee, staff_out_id "
    "ON parking_sessions FOR EACH ROW "
    "WHEN OLD.status = 'completed' AND ("
    "NEW.check_out_time IS NOT OLD.check_out_time "
    "OR NEW.parking_fee IS NOT OLD.parking_fee "
    "OR NEW.staff_out_id IS NOT OLD.staff_out_id) "
    "AND NOT (OLD.check_out_time IS NULL "
    "AND OLD.parking_fee IS NULL "
    "AND OLD.staff_out_id IS NULL "
    "AND NEW.status = 'completed' "
    "AND NEW.check_out_time IS NOT NULL "
    "AND NEW.parking_fee IS NOT NULL "
    "AND NEW.staff_out_id IS NOT NULL) "
    "BEGIN SELECT RAISE(ABORT, "
    "'completed parking session billing is immutable'); END"
)

UQ_CUSTOMERS_PHONE_NORMALIZED = "uq_customers_phone_normalized"
UQ_ROLES_NAME = "uq_roles_name"
UQ_VEHICLE_TYPES_NAME_NORMALIZED = "uq_vehicle_types_name_normalized"

TRG_ZONES_OPERATIONAL_UPDATE_GUARD = "trg_zones_operational_update_guard"
TRG_PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD = (
    "trg_parking_slots_operational_update_guard"
)
ZONES_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_ZONES_OPERATIONAL_UPDATE_GUARD} "
    "BEFORE UPDATE OF is_active ON zones FOR EACH ROW "
    "WHEN OLD.is_active = 1 AND NEW.is_active = 0 AND EXISTS ("
    "SELECT 1 FROM parking_slots "
    "WHERE zone_id = OLD.id AND (is_occupied = 1 OR EXISTS ("
    "SELECT 1 FROM parking_sessions "
    "WHERE parking_slot_id = parking_slots.id AND status = 'active'))) "
    "BEGIN SELECT RAISE(ABORT, 'zone has active parking'); END"
)
PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD} "
    "BEFORE UPDATE OF is_active, zone_id, vehicle_type_id ON parking_slots "
    "FOR EACH ROW WHEN ((OLD.is_active = 1 AND NEW.is_active = 0) "
    "OR NEW.zone_id != OLD.zone_id "
    "OR NEW.vehicle_type_id != OLD.vehicle_type_id) "
    "AND (OLD.is_occupied = 1 OR EXISTS ("
    "SELECT 1 FROM parking_sessions "
    "WHERE parking_slot_id = OLD.id AND status = 'active')) "
    "BEGIN SELECT RAISE(ABORT, 'slot has active parking'); END"
)

TRG_PARKING_SLOT_ZONE_IMMUTABLE_WITH_HISTORY = (
    "trg_parking_slots_zone_immutable_with_history"
)
PARKING_SLOT_ZONE_IMMUTABLE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS "
    f"{TRG_PARKING_SLOT_ZONE_IMMUTABLE_WITH_HISTORY} "
    "BEFORE UPDATE OF zone_id ON parking_slots FOR EACH ROW "
    "WHEN NEW.zone_id IS NOT OLD.zone_id AND EXISTS ("
    "SELECT 1 FROM parking_sessions WHERE parking_slot_id = OLD.id) "
    "BEGIN SELECT RAISE(ABORT, 'slot zone immutable after history'); END"
)

TRG_ZONE_CAPACITY_INTEGER_INSERT = "trg_zones_integer_capacity_insert"
TRG_ZONE_CAPACITY_INTEGER_UPDATE = "trg_zones_integer_capacity_update"
ZONE_CAPACITY_INTEGER_INSERT_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_ZONE_CAPACITY_INTEGER_INSERT} "
    "BEFORE INSERT ON zones FOR EACH ROW "
    "WHEN NEW.capacity IS NULL OR NEW.capacity < 0 "
    "OR NEW.capacity != CAST(NEW.capacity AS INTEGER) "
    "BEGIN SELECT RAISE(ABORT, 'zone capacity must be nonnegative integer'); END"
)
ZONE_CAPACITY_INTEGER_UPDATE_TRIGGER_SQL = (
    f"CREATE TRIGGER IF NOT EXISTS {TRG_ZONE_CAPACITY_INTEGER_UPDATE} "
    "BEFORE UPDATE OF capacity ON zones FOR EACH ROW "
    "WHEN NEW.capacity IS NULL OR NEW.capacity < 0 "
    "OR NEW.capacity != CAST(NEW.capacity AS INTEGER) "
    "BEGIN SELECT RAISE(ABORT, 'zone capacity must be nonnegative integer'); END"
)

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
        # --- roles: role name duy nhất như ORM contract ---
        role_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(roles)")
        }
        if role_columns:
            duplicate_roles = conn.exec_driver_sql(
                "SELECT name, group_concat(id), COUNT(*) FROM roles "
                "GROUP BY name HAVING COUNT(*) > 1"
            ).fetchall()
            if duplicate_roles:
                raise RuntimeError(
                    "Không thể tạo unique index cho roles.name vì dữ liệu "
                    f"legacy bị trùng: {duplicate_roles}. Cần đổi tên hoặc "
                    "gộp role thủ công rồi migration lại."
                )
            conn.exec_driver_sql(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {UQ_ROLES_NAME} "
                "ON roles(name)"
            )

        # --- vehicle_types: tên nghiệp vụ duy nhất sau NFC/casefold/trim ---
        vehicle_type_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(vehicle_types)")
        }
        if vehicle_type_columns:
            duplicate_vehicle_types = conn.exec_driver_sql(
                "SELECT unicode_casefold(name), group_concat(id), COUNT(*) "
                "FROM vehicle_types GROUP BY unicode_casefold(name) "
                "HAVING COUNT(*) > 1"
            ).fetchall()
            if duplicate_vehicle_types:
                raise RuntimeError(
                    "Không thể tạo unique index cho vehicle_types vì tên loại "
                    "xe bị trùng sau chuẩn hóa: "
                    f"{duplicate_vehicle_types}. Cần đổi tên thủ công rồi migration lại."
                )
            conn.exec_driver_sql(
                f"CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{UQ_VEHICLE_TYPES_NAME_NORMALIZED} "
                "ON vehicle_types(unicode_casefold(name))"
            )

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
            invalid_pass_prices = conn.exec_driver_sql(
                "SELECT id, price, typeof(price) FROM monthly_passes "
                "WHERE price IS NULL "
                "OR typeof(price) NOT IN ('integer', 'real') "
                "OR price < 0 OR price != CAST(price AS INTEGER) "
                f"OR price > {MAX_EXACT_VND}"
            ).fetchall()
            invalid_pass_dates = conn.exec_driver_sql(
                "SELECT id, start_date, end_date FROM monthly_passes "
                "WHERE start_date IS NULL OR end_date IS NULL "
                "OR typeof(start_date) != 'text' "
                "OR typeof(end_date) != 'text' "
                "OR start_date NOT GLOB "
                "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
                "OR end_date NOT GLOB "
                "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
                "OR substr(start_date, 1, 4) = '0000' "
                "OR substr(end_date, 1, 4) = '0000' "
                "OR date(start_date, '+0 days') IS NULL "
                "OR date(end_date, '+0 days') IS NULL "
                "OR date(start_date, '+0 days') != start_date "
                "OR date(end_date, '+0 days') != end_date "
                "OR end_date < start_date"
            ).fetchall()
            if invalid_pass_prices or invalid_pass_dates:
                raise RuntimeError(
                    "Không thể cài contract vé tháng vì dữ liệu legacy "
                    "không hợp lệ: giá="
                    f"{invalid_pass_prices}; khoảng ngày={invalid_pass_dates}. "
                    "Cần sửa thủ công rồi migration lại."
                )
            conn.exec_driver_sql(MONTHLY_PASS_PRICE_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(MONTHLY_PASS_PRICE_UPDATE_TRIGGER_SQL)
            conn.exec_driver_sql(MONTHLY_PASS_DATE_RANGE_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(MONTHLY_PASS_DATE_RANGE_UPDATE_TRIGGER_SQL)
            # Tên index phải khớp khai báo trong models/monthly_pass.py
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_monthly_passes_pass_code "
                "ON monthly_passes(pass_code) WHERE pass_code IS NOT NULL"
            )
            overlapping_passes = conn.exec_driver_sql(
                "SELECT first_pass.id, second_pass.id, first_pass.vehicle_id "
                "FROM monthly_passes AS first_pass "
                "JOIN monthly_passes AS second_pass "
                "ON first_pass.id < second_pass.id "
                "AND first_pass.vehicle_id = second_pass.vehicle_id "
                "AND first_pass.is_active = 1 "
                "AND second_pass.is_active = 1 "
                "AND first_pass.start_date <= second_pass.end_date "
                "AND first_pass.end_date >= second_pass.start_date"
            ).fetchall()
            if overlapping_passes:
                raise RuntimeError(
                    "Không thể cài trigger vé tháng vì các khoảng active "
                    "đang chồng nhau (id_1, id_2, vehicle_id): "
                    f"{overlapping_passes}. Cần xử lý thủ công trước khi "
                    "migration lại; hệ thống không tự xóa hay rút ngắn vé."
                )
            conn.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS "
                "trg_monthly_passes_no_overlap_insert "
                "BEFORE INSERT ON monthly_passes FOR EACH ROW "
                "WHEN NEW.is_active = 1 AND EXISTS ("
                "SELECT 1 FROM monthly_passes "
                "WHERE vehicle_id = NEW.vehicle_id AND is_active = 1 "
                "AND start_date <= NEW.end_date "
                "AND end_date >= NEW.start_date) "
                "BEGIN SELECT RAISE(ABORT, "
                "'monthly pass interval overlap'); END"
            )
            conn.exec_driver_sql(
                "CREATE TRIGGER IF NOT EXISTS "
                "trg_monthly_passes_no_overlap_update "
                "BEFORE UPDATE OF vehicle_id, start_date, end_date, is_active "
                "ON monthly_passes FOR EACH ROW "
                "WHEN NEW.is_active = 1 AND EXISTS ("
                "SELECT 1 FROM monthly_passes "
                "WHERE id != OLD.id "
                "AND vehicle_id = NEW.vehicle_id AND is_active = 1 "
                "AND start_date <= NEW.end_date "
                "AND end_date >= NEW.start_date) "
                "BEGIN SELECT RAISE(ABORT, "
                "'monthly pass interval overlap'); END"
            )

        # --- vehicles: loại xe bất biến sau khi phát sinh nghiệp vụ ---
        # Router trả 409 dễ hiểu; trigger là backstop cho TOCTOU và direct SQL.
        vehicle_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(vehicles)")
        }
        vehicle_session_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(parking_sessions)")
        }
        vehicle_pass_columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(monthly_passes)")
        }
        if vehicle_columns and vehicle_session_columns and vehicle_pass_columns:
            conn.exec_driver_sql(VEHICLE_TYPE_IMMUTABLE_TRIGGER_SQL)
        if vehicle_columns and vehicle_session_columns:
            conn.exec_driver_sql(VEHICLE_LICENSE_PLATE_IMMUTABLE_TRIGGER_SQL)

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
            if "price" not in price_columns:
                raise RuntimeError(
                    "Bảng price_configs legacy thiếu cột price; không thể "
                    "xác minh contract số nguyên VND."
                )
            invalid_prices = conn.exec_driver_sql(
                "SELECT id, price, typeof(price) FROM price_configs "
                "WHERE price IS NULL "
                "OR typeof(price) NOT IN ('integer', 'real') "
                "OR price < 0 "
                "OR price != CAST(price AS INTEGER) "
                f"OR price > {MAX_EXACT_VND}"
            ).fetchall()
            if invalid_prices:
                raise RuntimeError(
                    "Không thể nâng contract price_configs sang số nguyên "
                    "VND không âm vì có dữ liệu legacy không tương thích: "
                    f"{invalid_prices}. Không tự làm tròn; cần sửa dữ liệu "
                    "thủ công rồi khởi động lại."
                )
            invalid_ticket_types = conn.exec_driver_sql(
                "SELECT id, ticket_type FROM price_configs "
                "WHERE ticket_type IS NULL "
                "OR ticket_type NOT IN ('HOURLY', 'DAILY')"
            ).fetchall()
            if invalid_ticket_types:
                raise RuntimeError(
                    "Không thể cài contract price_configs.ticket_type vì "
                    "dữ liệu legacy ngoài HOURLY/DAILY: "
                    f"{invalid_ticket_types}."
                )
            invalid_effective_dates = conn.exec_driver_sql(
                "SELECT id, effective_date FROM price_configs "
                "WHERE effective_date IS NULL "
                "OR typeof(effective_date) != 'text' "
                "OR effective_date NOT GLOB "
                "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
                "OR substr(effective_date, 1, 4) = '0000' "
                "OR date(effective_date, '+0 days') IS NULL "
                "OR date(effective_date, '+0 days') != effective_date"
            ).fetchall()
            if invalid_effective_dates:
                raise RuntimeError(
                    "Không thể cài contract price_configs.effective_date "
                    "vì dữ liệu legacy không phải ngày YYYY-MM-DD hợp lệ: "
                    f"{invalid_effective_dates}."
                )
            conn.exec_driver_sql(PRICE_INTEGER_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_INTEGER_UPDATE_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_SAFE_VND_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_SAFE_VND_UPDATE_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_TICKET_TYPE_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_TICKET_TYPE_UPDATE_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(PRICE_EFFECTIVE_DATE_UPDATE_TRIGGER_SQL)
            if vehicle_columns and vehicle_session_columns:
                conn.exec_driver_sql(
                    PRICE_ACTIVE_SESSION_UPDATE_GUARD_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    PRICE_ACTIVE_SESSION_DELETE_GUARD_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    PRICE_ACTIVE_SESSION_REPLACE_GUARD_TRIGGER_SQL
                )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_price_config_one_active_per_vehicle_type "
                "ON price_configs(vehicle_type_id) WHERE is_active = 1"
            )

        # --- customers: số điện thoại duy nhất sau trim/casefold ---
        customer_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(customers)")
        }
        if customer_columns:
            if "phone_number" not in customer_columns:
                raise RuntimeError(
                    "Bảng customers legacy thiếu cột phone_number; không thể "
                    "xác minh unique phone chuẩn hóa."
                )
            invalid_phones = conn.exec_driver_sql(
                "SELECT id, phone_number FROM customers "
                "WHERE phone_number IS NULL "
                "OR unicode_casefold(phone_number) = ''"
            ).fetchall()
            duplicate_phones = conn.exec_driver_sql(
                "SELECT unicode_casefold(phone_number), group_concat(id), COUNT(*) "
                "FROM customers GROUP BY unicode_casefold(phone_number) "
                "HAVING COUNT(*) > 1"
            ).fetchall()
            if invalid_phones or duplicate_phones:
                raise RuntimeError(
                    "Không thể tạo unique index cho customers.phone_number: "
                    f"giá trị rỗng/null={invalid_phones}; trùng sau chuẩn hóa="
                    f"{duplicate_phones}. Cần sửa thủ công rồi migration lại."
                )
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                f"{UQ_CUSTOMERS_PHONE_NORMALIZED} "
                "ON customers(unicode_casefold(phone_number))"
            )

        # --- zones / parking_slots: mã định danh không trùng sau chuẩn hóa ---
        # API trim tên và so sánh không phân biệt hoa/thường. Hai expression
        # index này là backstop cho race giữa các request và đường ghi ngoài
        # API. Dữ liệu legacy vi phạm phải được dọn thủ công; không tự đổi tên.
        zone_columns = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(zones)")
        }
        if zone_columns:
            invalid_capacities = conn.exec_driver_sql(
                "SELECT id, capacity, typeof(capacity) FROM zones "
                "WHERE capacity IS NULL OR capacity < 0 "
                "OR typeof(capacity) NOT IN ('integer', 'real') "
                "OR capacity != CAST(capacity AS INTEGER)"
            ).fetchall()
            if invalid_capacities:
                raise RuntimeError(
                    "Không thể cài contract zones.capacity số nguyên không âm "
                    f"vì dữ liệu legacy không hợp lệ: {invalid_capacities}."
                )
            conn.exec_driver_sql(ZONE_CAPACITY_INTEGER_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(ZONE_CAPACITY_INTEGER_UPDATE_TRIGGER_SQL)
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
            if "parking_fee" not in session_columns:
                raise RuntimeError(
                    "Bảng parking_sessions legacy thiếu cột parking_fee; "
                    "không thể xác minh contract số nguyên VND."
                )
            session_lifecycle_ready = (
                SESSION_LIFECYCLE_COLUMNS <= session_columns
            )
            # Domain tiền được kiểm TRƯỚC state — cùng thứ tự ưu tiên với
            # trigger, nên một hàng legacy vừa sai tiền vừa thiếu state luôn
            # được báo bằng đúng lỗi tiền thay vì phụ thuộc thứ tự kiểm tra.
            invalid_fees = conn.exec_driver_sql(
                "SELECT id, parking_fee, typeof(parking_fee) "
                "FROM parking_sessions WHERE parking_fee IS NOT NULL AND ("
                "typeof(parking_fee) NOT IN ('integer', 'real') "
                "OR parking_fee < 0 "
                "OR parking_fee != CAST(parking_fee AS INTEGER) "
                f"OR parking_fee > {MAX_EXACT_VND})"
            ).fetchall()
            if invalid_fees:
                raise RuntimeError(
                    "Không thể nâng contract parking_sessions.parking_fee "
                    "sang số nguyên VND không âm vì có dữ liệu legacy không "
                    f"tương thích: {invalid_fees}. Không tự làm tròn; cần "
                    "sửa dữ liệu thủ công rồi migration lại."
                )
            invalid_statuses = conn.exec_driver_sql(
                "SELECT id, status FROM parking_sessions "
                "WHERE status IS NULL OR status NOT IN "
                "('active', 'completed', 'cancelled')"
            ).fetchall()
            invalid_datetimes: list = []
            invalid_states: list = []
            if session_lifecycle_ready:
                invalid_datetimes = conn.exec_driver_sql(
                    "SELECT id, check_in_time, check_out_time "
                    "FROM parking_sessions WHERE ("
                    f"{_sqlite_datetime_invalid('check_in_time')}) "
                    "OR (check_out_time IS NOT NULL AND ("
                    f"{_sqlite_datetime_invalid('check_out_time')}))"
                ).fetchall()
                invalid_states = conn.exec_driver_sql(
                    "SELECT id, status, check_out_time, parking_fee, "
                    "staff_out_id FROM parking_sessions WHERE "
                    "(status = 'completed' AND (check_out_time IS NULL "
                    "OR parking_fee IS NULL OR staff_out_id IS NULL "
                    "OR check_out_time < check_in_time)) "
                    "OR (status = 'active' AND (check_out_time IS NOT NULL "
                    "OR parking_fee IS NOT NULL OR staff_out_id IS NOT NULL))"
                ).fetchall()
            if invalid_statuses or invalid_datetimes or invalid_states:
                raise RuntimeError(
                    "Không thể cài contract vòng đời parking_sessions vì "
                    f"status sai={invalid_statuses}; datetime sai="
                    f"{invalid_datetimes}; state không đầy đủ={invalid_states}. "
                    "Cần sửa dữ liệu legacy thủ công trước rollout."
                )
            if columns and session_lifecycle_ready:
                invalid_pass_links = conn.exec_driver_sql(
                    "SELECT ps.id, ps.vehicle_id, ps.monthly_pass_id, "
                    "ps.check_in_time FROM parking_sessions AS ps "
                    "LEFT JOIN monthly_passes AS mp "
                    "ON mp.id = ps.monthly_pass_id "
                    "WHERE ps.monthly_pass_id IS NOT NULL AND ("
                    "mp.id IS NULL "
                    "OR mp.vehicle_id != ps.vehicle_id "
                    "OR date(ps.check_in_time) IS NULL "
                    "OR mp.start_date > date(ps.check_in_time) "
                    "OR mp.end_date < date(ps.check_in_time))"
                ).fetchall()
                if invalid_pass_links:
                    raise RuntimeError(
                        "Không thể cài contract quyền lợi phiên gửi xe vì "
                        "monthly_pass_id legacy không khớp xe/ngày check-in: "
                        f"{invalid_pass_links}. Cần sửa thủ công; migration "
                        "không tự gán hoặc xóa quyền lợi."
                    )
            if price_columns and vehicle_columns and session_lifecycle_ready:
                invalid_rate_links = conn.exec_driver_sql(
                    "SELECT ps.id, ps.vehicle_id, ps.check_in_time "
                    "FROM parking_sessions AS ps "
                    "JOIN vehicles AS v ON v.id = ps.vehicle_id "
                    "WHERE ps.status = 'active' "
                    "AND NOT EXISTS ("
                    "SELECT 1 FROM price_configs AS pc "
                    "WHERE pc.vehicle_type_id = v.vehicle_type_id "
                    "AND pc.is_active = 1 "
                    "AND pc.effective_date <= date(ps.check_in_time))"
                ).fetchall()
                if invalid_rate_links:
                    raise RuntimeError(
                        "Không thể cài contract bảng giá phiên gửi xe vì "
                        "có phiên active thiếu bảng giá dự phòng hiệu "
                        f"lực tại check-in: {invalid_rate_links}. Cần bổ sung "
                        "bảng giá hoặc xử lý phiên thủ công trước rollout."
                    )
            if zone_columns and slot_columns and vehicle_columns:
                invalid_slot_admissions = conn.exec_driver_sql(
                    "SELECT ps.id, ps.vehicle_id, ps.parking_slot_id "
                    "FROM parking_sessions AS ps "
                    "JOIN vehicles AS v ON v.id = ps.vehicle_id "
                    "LEFT JOIN parking_slots AS slot "
                    "ON slot.id = ps.parking_slot_id "
                    "LEFT JOIN zones AS z ON z.id = slot.zone_id "
                    "WHERE ps.status = 'active' "
                    "AND ps.parking_slot_id IS NOT NULL "
                    "AND (slot.id IS NULL OR z.id IS NULL "
                    "OR slot.vehicle_type_id != v.vehicle_type_id "
                    "OR slot.is_active != 1 OR z.is_active != 1)"
                ).fetchall()
                if invalid_slot_admissions:
                    raise RuntimeError(
                        "Không thể cài contract vị trí phiên gửi xe vì có "
                        "phiên active dùng vị trí/zone không hoạt động hoặc "
                        "không khớp loại xe: "
                        f"{invalid_slot_admissions}. Cần xử lý thủ công trước "
                        "rollout."
                    )
            if zone_columns and slot_columns:
                # Hai guard này khóa nhánh check-in commit trước trong
                # race với thao tác tắt/chuyển zone-slot. Nhánh admin
                # commit trước được conditional claim ở CRUD khóa bằng
                # expected zone/type snapshot.
                conn.exec_driver_sql(ZONES_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL)
                conn.exec_driver_sql(
                    PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL
                )
                conn.exec_driver_sql(PARKING_SLOT_ZONE_IMMUTABLE_TRIGGER_SQL)
            if columns:
                conn.exec_driver_sql(MONTHLY_PASS_HISTORY_IMMUTABLE_TRIGGER_SQL)
            conn.exec_driver_sql(PARKING_FEE_INTEGER_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(PARKING_FEE_INTEGER_UPDATE_TRIGGER_SQL)
            conn.exec_driver_sql(PARKING_FEE_SAFE_VND_INSERT_TRIGGER_SQL)
            conn.exec_driver_sql(PARKING_FEE_SAFE_VND_UPDATE_TRIGGER_SQL)
            if columns and session_lifecycle_ready:
                conn.exec_driver_sql(
                    SESSION_MONTHLY_PASS_INSERT_VALIDATION_TRIGGER_SQL
                )
            if price_columns and vehicle_columns and session_lifecycle_ready:
                conn.exec_driver_sql(
                    SESSION_RATE_INSERT_VALIDATION_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    SESSION_RATE_ACTIVATION_VALIDATION_TRIGGER_SQL
                )
            if zone_columns and slot_columns and vehicle_columns:
                conn.exec_driver_sql(
                    SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION_TRIGGER_SQL
                )
            conn.exec_driver_sql(
                SESSION_COMPLETED_STATUS_TERMINAL_TRIGGER_SQL
            )
            conn.exec_driver_sql(SESSION_STATUS_INSERT_VALIDATION_TRIGGER_SQL)
            conn.exec_driver_sql(SESSION_STATUS_UPDATE_VALIDATION_TRIGGER_SQL)
            if session_lifecycle_ready:
                conn.exec_driver_sql(SESSION_IDENTITY_IMMUTABLE_TRIGGER_SQL)
                conn.exec_driver_sql(
                    SESSION_COMPLETED_BILLING_IMMUTABLE_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    SESSION_DATETIME_INSERT_VALIDATION_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    SESSION_DATETIME_UPDATE_VALIDATION_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    SESSION_STATE_INSERT_VALIDATION_TRIGGER_SQL
                )
                conn.exec_driver_sql(
                    SESSION_STATE_UPDATE_VALIDATION_TRIGGER_SQL
                )
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

        # --- canonical BOOLEAN: chỉ chấp nhận INTEGER 0/1 ---
        for table_name, boolean_columns in BOOLEAN_DOMAIN_COLUMNS.items():
            existing_columns = {
                row[1]
                for row in conn.exec_driver_sql(
                    f"PRAGMA table_info({table_name})"
                )
            }
            if not existing_columns:
                continue
            missing_columns = set(boolean_columns) - existing_columns
            if missing_columns:
                raise RuntimeError(
                    f"Bảng {table_name} thiếu cột boolean bắt buộc: "
                    f"{sorted(missing_columns)}"
                )
            invalid_predicate = " OR ".join(
                f"{column} IS NULL OR typeof({column}) != 'integer' "
                f"OR {column} NOT IN (0, 1)"
                for column in boolean_columns
            )
            invalid_rows = conn.exec_driver_sql(
                f"SELECT id, {', '.join(boolean_columns)} FROM {table_name} "
                f"WHERE {invalid_predicate} ORDER BY id LIMIT 20"
            ).fetchall()
            if invalid_rows:
                raise RuntimeError(
                    f"Không thể cài contract boolean 0/1 cho {table_name}: "
                    f"{invalid_rows}. Cần sửa dữ liệu legacy thủ công."
                )
            table_prefix = f"trg_{table_name}_boolean_domain_"
            for trigger_name, trigger_sql in BOOLEAN_DOMAIN_TRIGGER_SQL.items():
                if trigger_name.startswith(table_prefix):
                    conn.exec_driver_sql(trigger_sql)
