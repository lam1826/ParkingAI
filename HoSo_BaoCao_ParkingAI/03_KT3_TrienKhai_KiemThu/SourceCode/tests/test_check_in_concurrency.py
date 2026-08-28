"""Regression test cho race condition check-in (Đợt 3).

Nguyên tắc của bộ test này:
- Dùng SQLite FILE TẠM (tmp_path), KHÔNG dùng engine in-memory dùng chung, vì
  hai thread phải có connection thật sự tách biệt.
- Mỗi worker có Session riêng; không share Session giữa các thread.
- Interleaving được điều phối bằng threading.Barrier gắn vào SQLAlchemy event
  `before_cursor_execute`: mỗi thread dừng ngay TRƯỚC câu ghi đầu tiên của nó
  (UPDATE parking_slots / INSERT parking_sessions). Nhờ đó cả hai transaction
  chắc chắn cùng tồn tại trong cửa sổ race, không phụ thuộc sleep() hay timing.
- Barrier đặt TRƯỚC lệnh ghi (chưa giữ write lock) nên không gây deadlock;
  nếu một thread thoát sớm, barrier được abort để thread còn lại chạy tiếp.
"""

import datetime
import threading

import bcrypt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

from database import Base, run_sqlite_migrations
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.price_config import PriceConfig
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.zone import Zone
from services.parking_service import ParkingService


class ConcurrentEnv:
    """Môi trường DB file tạm + tiện ích chạy hai request đồng thời."""

    def __init__(self, engine, session_factory, ids):
        self.engine = engine
        self.Session = session_factory
        self.__dict__.update(ids)

    # --- điều phối interleaving -------------------------------------------
    def run_pair(self, target, args_a, args_b, sync_on=None):
        """sync_on: các prefix SQL (uppercase) mà tại câu lệnh ĐẦU TIÊN khớp,
        mỗi thread sẽ dừng chờ thread kia. Mặc định đồng bộ ngay trước write
        đầu tiên của luồng check-in (claim slot / insert session) — cả hai
        thread cùng vượt qua toàn bộ bước kiểm tra đọc rồi mới ghi. Barrier
        đặt TRƯỚC khi write thực thi nên chưa thread nào giữ write lock —
        không deadlock."""
        if sync_on is None:
            sync_on = ("UPDATE PARKING_SLOTS", "INSERT INTO PARKING_SESSIONS")
        barrier = threading.Barrier(2)
        local = threading.local()

        @event.listens_for(self.engine, "before_cursor_execute")
        def sync_before_first_write(conn, cursor, statement, params, ctx, many):
            if getattr(local, "synced", False):
                return
            head = statement.lstrip().upper()
            if any(head.startswith(prefix) for prefix in sync_on):
                local.synced = True
                try:
                    barrier.wait(timeout=15)
                except threading.BrokenBarrierError:
                    pass  # bên kia đã thoát sớm — cứ chạy tiếp

        results = {}

        def wrap(idx, args):
            try:
                results[idx] = target(self, *args)
            except HTTPException as exc:
                results[idx] = ("HTTP", exc.status_code, str(exc.detail))
            except Exception as exc:  # noqa: BLE001 - ghi lại để assert
                results[idx] = ("EXC", type(exc).__name__, str(exc)[:200])
            finally:
                barrier.abort()

        threads = [
            threading.Thread(target=wrap, args=(0, args_a)),
            threading.Thread(target=wrap, args=(1, args_b)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=40)
        assert not any(t.is_alive() for t in threads), "Thread bị treo (deadlock?)"
        event.remove(self.engine, "before_cursor_execute", sync_before_first_write)
        return results[0], results[1]

    # --- tiện ích kiểm tra bất biến ---------------------------------------
    def audit(self):
        db = self.Session()
        try:
            per_slot = db.execute(
                select(ParkingSession.parking_slot_id, func.count(ParkingSession.id))
                .where(ParkingSession.status == "active")
                .group_by(ParkingSession.parking_slot_id)
            ).all()
            per_vehicle = db.execute(
                select(ParkingSession.vehicle_id, func.count(ParkingSession.id))
                .where(ParkingSession.status == "active")
                .group_by(ParkingSession.vehicle_id)
            ).all()
            occupied = {
                sid: bool(occ)
                for sid, occ in db.execute(
                    select(ParkingSlot.id, ParkingSlot.is_occupied)
                ).all()
            }
            return {
                "active_total": db.query(func.count(ParkingSession.id))
                .filter(ParkingSession.status == "active")
                .scalar(),
                "per_slot": {s: c for s, c in per_slot if s is not None},
                "per_vehicle": dict(per_vehicle),
                "occupied": occupied,
                "vehicles": db.query(func.count(Vehicle.id)).scalar(),
            }
        finally:
            db.close()

    def ensure_vehicle(self, plate):
        db = self.Session()
        try:
            v = db.execute(
                select(Vehicle).where(Vehicle.license_plate == plate)
            ).scalar_one_or_none()
            if v is None:
                v = Vehicle(license_plate=plate, vehicle_type_id=self.vt_id)
                db.add(v)
                db.commit()
                db.refresh(v)
            return v.id
        finally:
            db.close()

    def deactivate_slot(self, slot_id):
        db = self.Session()
        try:
            db.get(ParkingSlot, slot_id).is_active = False
            db.commit()
        finally:
            db.close()


@pytest.fixture()
def env(tmp_path):
    db_file = tmp_path / "race.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db = Session()
    role = Role(name="staff")
    db.add(role)
    db.commit()
    user = User(
        username="staff_race",
        full_name="Staff Race",
        role_id=role.id,
        password_hash=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode(),
        is_active=True,
    )
    vt = VehicleType(name="Ô tô race", description="test")
    zone = Zone(name="Khu Race", capacity=10, is_active=True)
    db.add_all([user, vt, zone])
    db.commit()
    db.add(
        PriceConfig(
            vehicle_type_id=vt.id,
            ticket_type="HOURLY",
            price=25_000,
            effective_date=datetime.date(2000, 1, 1),
            is_active=True,
        )
    )
    db.commit()
    slots = [
        ParkingSlot(
            zone_id=zone.id, vehicle_type_id=vt.id, slot_name=f"R-{i}",
            is_occupied=False, is_active=True,
        )
        for i in (1, 2)
    ]
    db.add_all(slots)
    db.commit()
    ids = {
        "user_id": user.id,
        "vt_id": vt.id,
        "zone_id": zone.id,
        "slot_a": slots[0].id,
        "slot_b": slots[1].id,
    }
    db.close()

    yield ConcurrentEnv(engine, Session, ids)
    engine.dispose()


# --- worker: luồng /parking/check-in (ParkingService) ----------------------
def service_check_in(env, plate, slot_id):
    db = env.Session()
    try:
        res = ParkingService(db).check_in(
            license_plate=plate,
            vehicle_type_id=env.vt_id,
            staff_id=env.user_id,
            parking_slot_id=slot_id,
        )
        return ("OK", 201, res["slot_id"])
    finally:
        db.close()


# --- worker: luồng /api/v1/parking-sessions/check-in (router + crud) -------
def router_check_in(env, vehicle_id, slot_id):
    from routers.parking_session import check_in_vehicle
    from schemas.parking_session import ParkingSessionCreate

    db = env.Session()
    try:
        user = db.get(User, env.user_id)
        res = check_in_vehicle(
            session_in=ParkingSessionCreate(
                vehicle_id=vehicle_id, parking_slot_id=slot_id
            ),
            db=db,
            current_user=user,
        )
        return ("OK", 201, res.parking_slot_id)
    finally:
        db.close()


def _statuses(a, b):
    return sorted([a[1], b[1]], key=str)


# ===========================================================================
# 1. Hai vehicle khác nhau + cùng explicit slot
# ===========================================================================


def test_two_vehicles_same_slot_service_flow(env):
    env.ensure_vehicle("51A-11111")
    env.ensure_vehicle("51B-22222")

    a, b = env.run_pair(
        service_check_in, ("51A-11111", env.slot_a), ("51B-22222", env.slot_a)
    )

    assert _statuses(a, b) == [201, 409], f"A={a} B={b}"
    audit = env.audit()
    assert audit["per_slot"] == {env.slot_a: 1}
    assert audit["occupied"][env.slot_a] is True
    assert audit["occupied"][env.slot_b] is False


def test_two_vehicles_same_slot_router_flow(env):
    v1 = env.ensure_vehicle("51G-77777")
    v2 = env.ensure_vehicle("51H-88888")

    a, b = env.run_pair(router_check_in, (v1, env.slot_a), (v2, env.slot_a))

    assert _statuses(a, b) == [201, 409], f"A={a} B={b}"
    audit = env.audit()
    assert audit["per_slot"] == {env.slot_a: 1}
    assert audit["occupied"][env.slot_a] is True


# ===========================================================================
# 2. Cùng vehicle + hai slot khác nhau
# ===========================================================================


def test_same_vehicle_two_slots_service_flow(env):
    env.ensure_vehicle("51C-33333")

    a, b = env.run_pair(
        service_check_in, ("51C-33333", env.slot_a), ("51C-33333", env.slot_b)
    )

    assert _statuses(a, b) == [201, 409], f"A={a} B={b}"
    audit = env.audit()
    assert audit["active_total"] == 1
    assert list(audit["per_vehicle"].values()) == [1]
    # Slot của transaction thua phải còn trống
    occupied_slots = [s for s, occ in audit["occupied"].items() if occ]
    assert len(occupied_slots) == 1
    assert set(audit["per_slot"]) == set(occupied_slots)


def test_same_vehicle_two_slots_router_flow(env):
    v1 = env.ensure_vehicle("51K-99999")

    a, b = env.run_pair(router_check_in, (v1, env.slot_a), (v1, env.slot_b))

    assert _statuses(a, b) == [201, 409], f"A={a} B={b}"
    audit = env.audit()
    assert audit["active_total"] == 1
    occupied_slots = [s for s, occ in audit["occupied"].items() if occ]
    assert len(occupied_slots) == 1


# ===========================================================================
# 3 & 4. Tự động cấp chỗ
# ===========================================================================


def test_auto_allocation_two_slots_both_succeed(env):
    env.ensure_vehicle("51X-11111")
    env.ensure_vehicle("51Y-22222")

    a, b = env.run_pair(service_check_in, ("51X-11111", None), ("51Y-22222", None))

    assert a[1] == 201 and b[1] == 201, f"A={a} B={b}"
    assert a[2] != b[2], "Hai xe phải được xếp vào hai slot khác nhau"
    audit = env.audit()
    assert audit["active_total"] == 2
    assert audit["per_slot"] == {env.slot_a: 1, env.slot_b: 1}
    assert all(audit["occupied"].values())


def test_auto_allocation_single_slot_one_wins(env):
    env.ensure_vehicle("51D-44444")
    env.ensure_vehicle("51E-55555")
    env.deactivate_slot(env.slot_b)

    a, b = env.run_pair(service_check_in, ("51D-44444", None), ("51E-55555", None))

    statuses = _statuses(a, b)
    assert 201 in statuses, f"A={a} B={b}"
    loser = [s for s in statuses if s != 201]
    assert loser and loser[0] in (404, 409), f"Lỗi nghiệp vụ mong đợi, nhận {statuses}"
    audit = env.audit()
    assert audit["active_total"] == 1
    assert audit["per_slot"] == {env.slot_a: 1}


# ===========================================================================
# 5. Cùng biển số xe MỚI, hai request đồng thời
# ===========================================================================


def test_same_new_license_plate_concurrent(env):
    # Race cần kiểm: cả hai request cùng thấy "biển số chưa tồn tại" rồi cùng
    # tạo xe mới -> đồng bộ ngay TRƯỚC INSERT INTO vehicles (write đầu tiên
    # của nhánh xe mới). Request thua unique(license_plate) phải dùng lại bản
    # ghi có sẵn và trả lỗi nghiệp vụ, không được 500.
    a, b = env.run_pair(
        service_check_in,
        ("51F-66666", env.slot_a),
        ("51F-66666", env.slot_b),
        sync_on=("INSERT INTO VEHICLES",),
    )

    statuses = _statuses(a, b)
    assert 201 in statuses, f"A={a} B={b}"
    assert 500 not in statuses, f"Không được trả 500: A={a} B={b}"
    audit = env.audit()
    assert audit["vehicles"] == 1, "Chỉ được tạo đúng một bản ghi vehicle"
    assert audit["active_total"] == 1
    occupied_slots = [s for s, occ in audit["occupied"].items() if occ]
    assert len(occupied_slots) == 1, "Slot của request thua không được occupied"


# ===========================================================================
# 6. DB backstop: insert thẳng bỏ qua API
# ===========================================================================


def _raw_session(env, vehicle_id, slot_id, status="active"):
    check_in_time = __import__("datetime").datetime.now()
    session = ParkingSession(
        vehicle_id=vehicle_id,
        parking_slot_id=slot_id,
        check_in_time=check_in_time,
        status=status,
        staff_in_id=env.user_id,
    )
    if status == "completed":
        # Contract vòng đời ở tầng DB: phiên completed phải có ĐỦ billing
        # (check_out_time >= check_in_time, parking_fee, staff_out_id).
        # Fixture lịch sử phải tôn trọng contract thay vì làm yếu trigger.
        session.check_out_time = check_in_time
        session.parking_fee = 0
        session.staff_out_id = env.user_id
    return session


def test_index_blocks_second_active_session_per_vehicle(env):
    v = env.ensure_vehicle("51M-10001")
    db = env.Session()
    try:
        db.add(_raw_session(env, v, env.slot_a))
        db.commit()
        db.add(_raw_session(env, v, env.slot_b))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()
    assert env.audit()["active_total"] == 1


def test_index_blocks_second_active_session_per_slot(env):
    v1 = env.ensure_vehicle("51M-10002")
    v2 = env.ensure_vehicle("51M-10003")
    db = env.Session()
    try:
        db.add(_raw_session(env, v1, env.slot_a))
        db.commit()
        db.add(_raw_session(env, v2, env.slot_a))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()
    assert env.audit()["per_slot"] == {env.slot_a: 1}


def test_index_allows_many_completed_sessions_in_history(env):
    v = env.ensure_vehicle("51M-10004")
    db = env.Session()
    try:
        for _ in range(3):
            db.add(_raw_session(env, v, env.slot_a, status="completed"))
            db.commit()
        db.add(_raw_session(env, v, env.slot_a))  # một active là hợp lệ
        db.commit()
    finally:
        db.close()
    audit = env.audit()
    assert audit["active_total"] == 1
    assert audit["per_slot"] == {env.slot_a: 1}


def test_index_vehicle_invariant_holds_for_sessions_without_slot(env):
    """parking_slot_id NULL không được lách bất biến một-phiên-active-mỗi-xe."""
    v = env.ensure_vehicle("51M-10005")
    db = env.Session()
    try:
        db.add(_raw_session(env, v, None))
        db.commit()
        db.add(_raw_session(env, v, None))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()
    assert env.audit()["active_total"] == 1


def test_index_allows_multiple_null_slot_sessions_for_different_vehicles(env):
    """Index theo slot dùng WHERE parking_slot_id IS NOT NULL nên nhiều phiên
    active không gắn slot (xe khác nhau) vẫn hợp lệ."""
    v1 = env.ensure_vehicle("51M-10006")
    v2 = env.ensure_vehicle("51M-10007")
    db = env.Session()
    try:
        db.add(_raw_session(env, v1, None))
        db.add(_raw_session(env, v2, None))
        db.commit()
    finally:
        db.close()
    assert env.audit()["active_total"] == 2


# ===========================================================================
# 7. Rollback: INSERT session thất bại sau khi claim slot
# ===========================================================================


def test_slot_released_when_session_insert_fails(env):
    """Ép INSERT parking_sessions thất bại sau khi slot đã được claim; slot
    phải trở lại free và không còn session rác."""
    env.ensure_vehicle("51N-20001")
    blocker_vehicle = env.ensure_vehicle("51N-20002")

    # Chiếm sẵn slot_b bằng một phiên active hợp lệ, rồi ép phiên mới trùng
    # slot đó ở tầng DB thông qua sửa trực tiếp sau khi claim: dùng event để
    # làm INSERT thất bại một cách xác định.
    db = env.Session()
    try:
        db.add(_raw_session(env, blocker_vehicle, env.slot_b))
        db.commit()
    finally:
        db.close()

    fail_once = {"done": False}

    @event.listens_for(env.engine, "before_cursor_execute")
    def break_session_insert(conn, cursor, statement, params, ctx, many):
        if fail_once["done"]:
            return
        if statement.lstrip().upper().startswith("INSERT INTO PARKING_SESSIONS"):
            fail_once["done"] = True
            raise OperationalError("forced failure", {}, Exception("ép lỗi INSERT"))

    try:
        with pytest.raises(HTTPException) as exc_info:
            service_check_in(env, "51N-20001", env.slot_a)
        assert exc_info.value.status_code >= 400
    finally:
        event.remove(env.engine, "before_cursor_execute", break_session_insert)

    audit = env.audit()
    assert audit["occupied"][env.slot_a] is False, "Slot phải được trả lại khi rollback"
    assert audit["per_slot"] == {env.slot_b: 1}, "Không được để session rác"


# ===========================================================================
# 8. Migration cho DB legacy
# ===========================================================================


def _legacy_engine(tmp_path, name="legacy.db"):
    engine = create_engine(f"sqlite:///{(tmp_path / name).as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE parking_sessions ("
            " id VARCHAR(36) PRIMARY KEY, vehicle_id INTEGER NOT NULL,"
            " parking_slot_id INTEGER, monthly_pass_id INTEGER,"
            " check_in_time DATETIME, check_out_time DATETIME,"
            " image_in_url VARCHAR(255), image_out_url VARCHAR(255),"
            " parking_fee FLOAT, status VARCHAR(20), staff_in_id INTEGER,"
            " staff_out_id INTEGER, created_at DATETIME, updated_at DATETIME)"
        )
    return engine


def test_migration_creates_session_indexes_and_is_idempotent(tmp_path):
    engine = _legacy_engine(tmp_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO parking_sessions (id, vehicle_id, parking_slot_id,"
            " check_in_time, status, staff_in_id)"
            " VALUES ('s1', 1, 1, '2026-01-01 08:00:00', 'active', 1)"
        )

    run_sqlite_migrations(engine)
    run_sqlite_migrations(engine)  # idempotent

    with engine.begin() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='parking_sessions'"
            )
        }
        trigger_names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
                " AND tbl_name='parking_sessions'"
            )
        }
    assert "uq_parking_session_one_active_per_vehicle" in names
    assert "uq_parking_session_one_active_per_slot" in names
    assert "trg_parking_sessions_integer_fee_insert" in trigger_names
    assert "trg_parking_sessions_integer_fee_update" in trigger_names

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO parking_sessions (id, vehicle_id, parking_slot_id,"
                " check_in_time, status, staff_in_id)"
                " VALUES ('s2', 2, 1, '2026-01-01 09:00:00', 'active', 1)"
            )

    with pytest.raises(IntegrityError, match="parking fee must be nonnegative integer"):
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE parking_sessions SET parking_fee = 1000.5 WHERE id = 's1'"
            )
    engine.dispose()


def test_migration_fails_loudly_on_fractional_legacy_parking_fee(tmp_path):
    engine = _legacy_engine(tmp_path, "legacy_fractional_fee.db")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO parking_sessions (id, vehicle_id, parking_slot_id,"
            " check_in_time, parking_fee, status, staff_in_id)"
            " VALUES ('fee-legacy', 1, 1, '2026-01-01 08:00:00',"
            " 1000.5, 'completed', 1)"
        )

    with pytest.raises(
        RuntimeError,
        match=r"parking_sessions\.parking_fee.*fee-legacy|fee-legacy.*parking_fee",
    ):
        run_sqlite_migrations(engine)

    with engine.connect() as conn:
        stored = conn.exec_driver_sql(
            "SELECT parking_fee, typeof(parking_fee) "
            "FROM parking_sessions WHERE id = 'fee-legacy'"
        ).one()
        trigger_names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
                " AND tbl_name='parking_sessions'"
            )
        }

    assert stored == (1000.5, "real")
    assert "trg_parking_sessions_integer_fee_insert" not in trigger_names
    assert "trg_parking_sessions_integer_fee_update" not in trigger_names
    engine.dispose()


def test_migration_fails_loudly_on_legacy_duplicates(tmp_path):
    """DB legacy đã vi phạm bất biến: migration phải fail rõ ràng, KHÔNG tự
    xóa/sửa dữ liệu để 'dọn đường' cho index."""
    engine = _legacy_engine(tmp_path, "legacy_dup.db")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO parking_sessions (id, vehicle_id, parking_slot_id,"
            " check_in_time, status, staff_in_id)"
            " VALUES ('d1', 7, 3, '2026-01-01 08:00:00', 'active', 1),"
            "        ('d2', 8, 3, '2026-01-01 08:30:00', 'active', 1)"
        )

    with pytest.raises(Exception) as exc_info:
        run_sqlite_migrations(engine)
    message = str(exc_info.value)
    assert "parking_sessions" in message
    # Thông báo phải đủ thông tin để quản trị viên dọn dữ liệu
    assert "3" in message or "slot" in message.lower()

    with engine.begin() as conn:
        remaining = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM parking_sessions"
        ).scalar()
    assert remaining == 2, "Migration không được xóa/sửa dữ liệu legacy"
    engine.dispose()
