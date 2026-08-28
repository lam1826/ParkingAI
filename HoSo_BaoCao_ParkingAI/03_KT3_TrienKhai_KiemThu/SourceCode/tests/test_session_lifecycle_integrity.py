"""Contract vòng đời `parking_sessions`: active -> checking_out -> completed.

Tách riêng khỏi `test_check_out*.py` (tập trung vào phí/đồng thời) vì các test ở
đây khẳng định MỘT trách nhiệm: trạng thái phiên gửi xe chỉ đi đúng đường đã
định, ở cả tầng API lẫn tầng DB, và mọi đường ghi khác đều bị từ chối bằng đúng
thông báo của trigger sở hữu bất biến đó.

Thứ tự ưu tiên trigger (SQLite KHÔNG đảm bảo thứ tự nổ giữa nhiều BEFORE
trigger, nên các WHEN được viết rời nhau — xem backend/database.py):

1. domain tiền        -> 'parking fee must be nonnegative integer'
                         / 'parking fee exceeds exact VND range'
2. hàng đã completed  -> 'completed parking session is terminal'
                         / 'completed parking session billing is immutable'
                         / 'parking session identity is immutable'
3. domain datetime    -> 'parking session datetime invalid'
4. domain/transition status -> 'parking session status invalid'
5. state đầy đủ       -> 'parking session state incomplete'

Không test nào ở đây chạm hai database thật: toàn bộ dùng SQLite in-memory của
conftest hoặc file trong `tmp_path` của pytest.
"""

import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import crud.parking_session as crud_session
from database import Base, run_sqlite_migrations
from db_rollout import check_database_readiness
from models.parking_session import ParkingSession
from models.parking_slot import ParkingSlot
from models.price_config import PriceConfig
from models.role import Role
from models.user import User
from models.vehicle import Vehicle
from models.vehicle_type import VehicleType
from models.zone import Zone
from services.auth_service import AuthService
from services.parking_service import ParkingService


CANONICAL_SQLITE_DATETIME = "%Y-%m-%d %H:%M:%S.%f"


def _as_sqlite_datetime(value: datetime.datetime) -> str:
    """Đúng dạng text canonical mà SQLAlchemy ghi cho cột DateTime SQLite."""
    return value.strftime(CANONICAL_SQLITE_DATETIME)


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    token = AuthService().create_access_token(
        user_id=test_user.id,
        username=test_user.username,
        role=str(test_user.role),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def statuses_seen_while_billing(monkeypatch) -> list[str]:
    """Ghi lại status ĐÃ PERSIST tại đúng thời điểm tính phí.

    `calculate_fee` chạy sau khi claim `active -> checking_out` và trước khi
    commit, nên đọc trong cùng transaction là cách quan sát trạng thái chuyển
    tiếp mà không cần nới lỏng bất kỳ ràng buộc nào.
    """
    observed: list[str] = []
    original = ParkingService.calculate_fee

    def spy(self, *args, **kwargs):
        observed.extend(
            row[0]
            for row in self.db.execute(
                text("SELECT status FROM parking_sessions")
            ).all()
        )
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ParkingService, "calculate_fee", spy)
    return observed


def _persisted_statuses(db: Session) -> list[str]:
    return [
        row[0]
        for row in db.execute(text("SELECT status FROM parking_sessions")).all()
    ]


# ===========================================================================
# 1. active -> checking_out -> completed trên CẢ HAI endpoint check-out
# ===========================================================================


def test_post_checkout_goes_through_checking_out_to_completed(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle: Vehicle,
    parking_session: ParkingSession,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
    statuses_seen_while_billing: list[str],
):
    assert parking_session.status == "active"

    response = client.post(
        "/parking/check-out",
        json={"license_plate": vehicle.license_plate},
        headers=auth_headers,
    )

    assert response.status_code == 200
    # Trạng thái chuyển tiếp CÓ tồn tại trong transaction...
    assert statuses_seen_while_billing == ["checking_out"]

    db_session.expire_all()
    persisted = db_session.get(ParkingSession, parking_session.id)
    # ...và KHÔNG được sống sót sau khi request kết thúc.
    assert persisted.status == "completed"
    assert persisted.check_out_time is not None
    assert persisted.parking_fee is not None
    assert persisted.staff_out_id is not None
    assert _persisted_statuses(db_session) == ["completed"]
    assert db_session.get(ParkingSlot, parking_slot.id).is_occupied is False


def test_put_checkout_goes_through_checking_out_to_completed(
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    parking_session: ParkingSession,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
    statuses_seen_while_billing: list[str],
):
    response = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert statuses_seen_while_billing == ["checking_out"]

    db_session.expire_all()
    persisted = db_session.get(ParkingSession, parking_session.id)
    assert persisted.status == "completed"
    assert persisted.check_out_time is not None
    assert persisted.parking_fee is not None
    assert persisted.staff_out_id is not None
    assert _persisted_statuses(db_session) == ["completed"]
    assert db_session.get(ParkingSlot, parking_slot.id).is_occupied is False


@pytest.mark.parametrize("endpoint", ["post", "put"])
def test_checkout_survives_production_autoflush_settings(
    endpoint: str,
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle: Vehicle,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    """`SessionLocal` production dùng autoflush MẶC ĐỊNH (True).

    Fixture test lại tạo session với `autoflush=False`, nên một flush ngầm xảy
    ra giữa lúc claim `checking_out` và lúc commit sẽ không bao giờ lộ ra trong
    suite nếu không có test này. Bật autoflush đúng như production để đường
    check-out được kiểm ở cùng cấu hình session mà người dùng thật chạy.
    """
    db_session.autoflush = True
    try:
        if endpoint == "post":
            response = client.post(
                "/parking/check-out",
                json={"license_plate": vehicle.license_plate},
                headers=auth_headers,
            )
        else:
            response = client.put(
                f"/api/v1/parking-sessions/{parking_session.id}/check-out",
                json={},
                headers=auth_headers,
            )
    finally:
        db_session.autoflush = False

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(ParkingSession, parking_session.id).status == "completed"


# ===========================================================================
# 2. Tính phí lỗi -> rollback về active, slot vẫn occupied, không billing dở
# ===========================================================================


@pytest.mark.parametrize("endpoint", ["post", "put"])
def test_fee_failure_rolls_session_back_to_active(
    endpoint: str,
    monkeypatch,
    client: TestClient,
    auth_headers: dict,
    db_session: Session,
    vehicle: Vehicle,
    parking_session: ParkingSession,
    parking_slot: ParkingSlot,
    price_config: PriceConfig,
):
    def failing_fee(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Chưa cấu hình bảng giá.")

    monkeypatch.setattr(ParkingService, "calculate_fee", failing_fee)

    if endpoint == "post":
        response = client.post(
            "/parking/check-out",
            json={"license_plate": vehicle.license_plate},
            headers=auth_headers,
        )
    else:
        response = client.put(
            f"/api/v1/parking-sessions/{parking_session.id}/check-out",
            json={},
            headers=auth_headers,
        )

    assert response.status_code == 404

    db_session.expire_all()
    persisted = db_session.get(ParkingSession, parking_session.id)
    assert persisted.status == "active"
    assert persisted.check_out_time is None
    assert persisted.parking_fee is None
    assert persisted.staff_out_id is None
    # Không để lại trạng thái chuyển tiếp, và xe vẫn đang giữ chỗ.
    assert _persisted_statuses(db_session) == ["active"]
    assert db_session.get(ParkingSlot, parking_slot.id).is_occupied is True


# ===========================================================================
# 3. Domain và transition của status ở tầng DB
# ===========================================================================


def _insert_session_sql(status_value: str) -> str:
    return (
        "INSERT INTO parking_sessions "
        "(id, vehicle_id, parking_slot_id, check_in_time, status, staff_in_id) "
        f"VALUES (:id, :vehicle_id, NULL, :check_in_time, '{status_value}', "
        ":staff_in_id)"
    )


@pytest.mark.parametrize("bad_status", ["actve", "CHECKING_OUT", "", "done"])
def test_db_rejects_status_typo_on_insert(
    bad_status: str,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    with pytest.raises(IntegrityError, match="parking session status invalid"):
        db_session.execute(
            text(_insert_session_sql(bad_status)),
            {
                "id": f"typo-{bad_status or 'empty'}",
                "vehicle_id": vehicle.id,
                "check_in_time": _as_sqlite_datetime(business_reference_now),
                "staff_in_id": test_user.id,
            },
        )
        db_session.commit()
    db_session.rollback()


def test_db_rejects_direct_insert_of_transition_status(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """`checking_out` chỉ hợp lệ khi được claim từ `active`, không bao giờ INSERT."""
    with pytest.raises(IntegrityError, match="parking session status invalid"):
        db_session.execute(
            text(_insert_session_sql("checking_out")),
            {
                "id": "direct-checking-out",
                "vehicle_id": vehicle.id,
                "check_in_time": _as_sqlite_datetime(business_reference_now),
                "staff_in_id": test_user.id,
            },
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == []


def test_db_rejects_status_typo_on_update(
    db_session: Session,
    parking_session: ParkingSession,
):
    with pytest.raises(IntegrityError, match="parking session status invalid"):
        db_session.execute(
            text("UPDATE parking_sessions SET status='actve' WHERE id=:id"),
            {"id": parking_session.id},
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["active"]


def _complete_session(db: Session, session: ParkingSession, staff_id: int) -> None:
    """Hoàn tất phiên bằng MỘT câu UPDATE đủ billing — đường ghi hợp lệ duy nhất."""
    db.execute(
        text(
            "UPDATE parking_sessions SET status='completed', "
            "check_out_time=:check_out_time, parking_fee=0, "
            "staff_out_id=:staff_out_id WHERE id=:id"
        ),
        {
            "check_out_time": _as_sqlite_datetime(session.check_in_time),
            "staff_out_id": staff_id,
            "id": session.id,
        },
    )
    db.commit()


@pytest.mark.parametrize(
    ("target_status", "expected_message"),
    [
        ("active", "completed parking session is terminal"),
        ("cancelled", "completed parking session is terminal"),
        ("checking_out", "completed parking session is terminal"),
        ("actve", "completed parking session is terminal"),
    ],
)
def test_db_keeps_completed_session_terminal_for_every_target_status(
    target_status: str,
    expected_message: str,
    db_session: Session,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    _complete_session(db_session, parking_session, test_user.id)

    with pytest.raises(IntegrityError, match=expected_message):
        db_session.execute(
            text("UPDATE parking_sessions SET status=:status WHERE id=:id"),
            {"status": target_status, "id": parking_session.id},
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["completed"]


@pytest.mark.parametrize("target_status", ["active", "cancelled", "completed"])
def test_db_rejects_leaving_checking_out_for_anything_but_completed(
    target_status: str,
    db_session: Session,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    """`checking_out` chỉ có đúng một lối ra hợp lệ: `completed` đủ billing."""
    assert crud_session.claim_session_for_checkout(db_session, parking_session.id)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.execute(
            text("UPDATE parking_sessions SET status=:status WHERE id=:id"),
            {"status": target_status, "id": parking_session.id},
        )
        db_session.commit()
    if target_status == "completed":
        # Lối ra đúng nhưng thiếu billing -> bị trigger state chặn.
        assert "parking session state incomplete" in str(exc_info.value)
    else:
        assert "parking session status invalid" in str(exc_info.value)
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["active"]


def test_db_rejects_entering_checking_out_from_non_active(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    db_session.execute(
        text(_insert_session_sql("cancelled")),
        {
            "id": "cancelled-session",
            "vehicle_id": vehicle.id,
            "check_in_time": _as_sqlite_datetime(business_reference_now),
            "staff_in_id": test_user.id,
        },
    )
    db_session.commit()

    with pytest.raises(IntegrityError, match="parking session status invalid"):
        db_session.execute(
            text(
                "UPDATE parking_sessions SET status='checking_out' WHERE id=:id"
            ),
            {"id": "cancelled-session"},
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["cancelled"]


def test_claim_for_checkout_only_wins_once(
    db_session: Session,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    assert crud_session.claim_session_for_checkout(db_session, parking_session.id)
    assert not crud_session.claim_session_for_checkout(db_session, parking_session.id)
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["active"]


# ===========================================================================
# 4. Domain datetime — cô lập bằng phiên `cancelled` (không kích trigger khác)
# ===========================================================================


MALFORMED_DATETIMES = [
    pytest.param("khong-phai-thoi-gian", id="text-rac"),
    pytest.param("2026-02-30 08:00:00", id="ngay-khong-ton-tai"),
    pytest.param("0000-01-01 08:00:00", id="nam-0000"),
    pytest.param("2026-08-25 08:00:00+07:00", id="co-offset-timezone"),
    pytest.param("2026-08-25T08:00:00", id="dung-chu-T"),
    pytest.param("2026-08-25 08:00:00.", id="dau-cham-treo"),
]


@pytest.mark.parametrize("bad_value", MALFORMED_DATETIMES)
def test_db_rejects_malformed_check_in_time(
    bad_value: str,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
):
    with pytest.raises(IntegrityError, match="parking session datetime invalid"):
        db_session.execute(
            text(_insert_session_sql("cancelled")),
            {
                "id": "bad-check-in",
                "vehicle_id": vehicle.id,
                "check_in_time": bad_value,
                "staff_in_id": test_user.id,
            },
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == []


@pytest.mark.parametrize("bad_value", MALFORMED_DATETIMES)
def test_db_rejects_malformed_check_out_time(
    bad_value: str,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    with pytest.raises(IntegrityError, match="parking session datetime invalid"):
        db_session.execute(
            text(
                "INSERT INTO parking_sessions (id, vehicle_id, parking_slot_id, "
                "check_in_time, check_out_time, status, staff_in_id) "
                "VALUES (:id, :vehicle_id, NULL, :check_in_time, "
                ":check_out_time, 'cancelled', :staff_in_id)"
            ),
            {
                "id": "bad-check-out",
                "vehicle_id": vehicle.id,
                "check_in_time": _as_sqlite_datetime(business_reference_now),
                "check_out_time": bad_value,
                "staff_in_id": test_user.id,
            },
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == []


def test_db_accepts_canonical_naive_datetime(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    """Control case: đúng dạng canonical thì KHÔNG bị trigger datetime chặn."""
    db_session.execute(
        text(_insert_session_sql("cancelled")),
        {
            "id": "canonical-datetime",
            "vehicle_id": vehicle.id,
            "check_in_time": _as_sqlite_datetime(business_reference_now),
            "staff_in_id": test_user.id,
        },
    )
    db_session.commit()
    assert _persisted_statuses(db_session) == ["cancelled"]


# ===========================================================================
# 5. State đầy đủ của phiên completed
# ===========================================================================


COMPLETED_COLUMNS = ("check_out_time", "parking_fee", "staff_out_id")


@pytest.mark.parametrize("missing_column", COMPLETED_COLUMNS)
def test_db_rejects_completed_insert_missing_any_billing_field(
    missing_column: str,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    price_config: PriceConfig,
    business_reference_now: datetime.datetime,
):
    values = {
        "check_out_time": _as_sqlite_datetime(business_reference_now),
        "parking_fee": 0,
        "staff_out_id": test_user.id,
    }
    values[missing_column] = None

    with pytest.raises(IntegrityError, match="parking session state incomplete"):
        db_session.execute(
            text(
                "INSERT INTO parking_sessions (id, vehicle_id, parking_slot_id, "
                "check_in_time, check_out_time, parking_fee, status, "
                "staff_in_id, staff_out_id) "
                "VALUES (:id, :vehicle_id, NULL, :check_in_time, "
                ":check_out_time, :parking_fee, 'completed', :staff_in_id, "
                ":staff_out_id)"
            ),
            {
                "id": f"incomplete-{missing_column}",
                "vehicle_id": vehicle.id,
                "check_in_time": _as_sqlite_datetime(business_reference_now),
                "staff_in_id": test_user.id,
                **values,
            },
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == []


@pytest.mark.parametrize("missing_column", COMPLETED_COLUMNS)
def test_db_rejects_completing_an_active_session_without_full_billing(
    missing_column: str,
    db_session: Session,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    assignments = {
        "check_out_time": ":check_out_time",
        "parking_fee": "0",
        "staff_out_id": ":staff_out_id",
    }
    assignments.pop(missing_column)
    set_clause = ", ".join(
        f"{column}={value}" for column, value in assignments.items()
    )

    with pytest.raises(IntegrityError, match="parking session state incomplete"):
        db_session.execute(
            text(
                f"UPDATE parking_sessions SET status='completed', {set_clause} "
                "WHERE id=:id"
            ),
            {
                "check_out_time": _as_sqlite_datetime(
                    parking_session.check_in_time
                ),
                "staff_out_id": test_user.id,
                "id": parking_session.id,
            },
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["active"]


def test_db_rejects_check_out_time_before_check_in_time(
    db_session: Session,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    earlier = parking_session.check_in_time - datetime.timedelta(seconds=1)

    with pytest.raises(IntegrityError, match="parking session state incomplete"):
        db_session.execute(
            text(
                "UPDATE parking_sessions SET status='completed', "
                "check_out_time=:check_out_time, parking_fee=0, "
                "staff_out_id=:staff_out_id WHERE id=:id"
            ),
            {
                "check_out_time": _as_sqlite_datetime(earlier),
                "staff_out_id": test_user.id,
                "id": parking_session.id,
            },
        )
        db_session.commit()
    db_session.rollback()
    assert _persisted_statuses(db_session) == ["active"]


def test_db_rejects_billing_on_a_session_that_is_still_active(
    db_session: Session,
    test_user: User,
    parking_session: ParkingSession,
    price_config: PriceConfig,
):
    """Phí hợp lệ nhưng phiên chưa completed vẫn là state sai (không phải lỗi tiền)."""
    with pytest.raises(IntegrityError, match="parking session state incomplete"):
        db_session.execute(
            text("UPDATE parking_sessions SET parking_fee=25000 WHERE id=:id"),
            {"id": parking_session.id},
        )
        db_session.commit()
    db_session.rollback()
    assert db_session.get(ParkingSession, parking_session.id).parking_fee is None


# ===========================================================================
# 6. Preflight/readiness từ chối dữ liệu legacy hỏng và `checking_out` đọng lại
# ===========================================================================


def _legacy_sessions_engine(tmp_path: Path, name: str):
    engine = create_engine(f"sqlite:///{(tmp_path / name).as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE parking_sessions ("
            " id VARCHAR(36) PRIMARY KEY, vehicle_id INTEGER NOT NULL,"
            " parking_slot_id INTEGER, monthly_pass_id INTEGER,"
            " check_in_time DATETIME, check_out_time DATETIME,"
            " image_in_url VARCHAR(255), image_out_url VARCHAR(255),"
            " parking_fee INTEGER, status VARCHAR(20), staff_in_id INTEGER,"
            " staff_out_id INTEGER, created_at DATETIME, updated_at DATETIME)"
        )
    return engine


def test_migration_refuses_legacy_row_stuck_in_checking_out(tmp_path: Path):
    engine = _legacy_sessions_engine(tmp_path, "legacy-checking-out.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, status,"
            " staff_in_id) VALUES ('stuck', 1, '2026-01-01 08:00:00.000000',"
            " 'checking_out', 1)"
        )

    with pytest.raises(RuntimeError, match="status sai=.*stuck"):
        run_sqlite_migrations(engine)
    engine.dispose()


def test_migration_refuses_legacy_completed_row_without_billing(tmp_path: Path):
    engine = _legacy_sessions_engine(tmp_path, "legacy-incomplete-completed.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, status,"
            " staff_in_id) VALUES ('half-done', 1, '2026-01-01 08:00:00.000000',"
            " 'completed', 1)"
        )

    with pytest.raises(RuntimeError, match="state không đầy đủ=.*half-done"):
        run_sqlite_migrations(engine)
    engine.dispose()


def test_migration_refuses_legacy_malformed_check_in_time(tmp_path: Path):
    engine = _legacy_sessions_engine(tmp_path, "legacy-bad-datetime.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO parking_sessions (id, vehicle_id, check_in_time, status,"
            " staff_in_id) VALUES ('bad-time', 1, '0000-01-01 08:00:00',"
            " 'active', 1)"
        )

    with pytest.raises(RuntimeError, match="datetime sai=.*bad-time"):
        run_sqlite_migrations(engine)
    engine.dispose()


def _seeded_database(tmp_path: Path, name: str):
    """DB file hợp lệ, đủ trigger, với một phiên active không gắn slot."""
    database_path = tmp_path / name
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)

    reference = datetime.datetime(2026, 8, 25, 8, 0, 0)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = factory()
    try:
        role = Role(name="staff")
        db.add(role)
        db.flush()
        user = User(
            username="readiness_staff",
            role_id=role.id,
            password_hash="x" * 40,
            full_name="Readiness",
            is_active=True,
        )
        vehicle_type = VehicleType(name="Ô tô", description="readiness")
        zone = Zone(name="Khu R", capacity=5, is_active=True)
        db.add_all([user, vehicle_type, zone])
        db.flush()
        vehicle = Vehicle(license_plate="51R-00001", vehicle_type_id=vehicle_type.id)
        db.add(vehicle)
        db.add(
            PriceConfig(
                vehicle_type_id=vehicle_type.id,
                is_active=True,
                ticket_type="HOURLY",
                price=25000,
                effective_date=(reference - datetime.timedelta(days=1)).date(),
            )
        )
        db.flush()
        session = ParkingSession(
            vehicle_id=vehicle.id,
            parking_slot_id=None,
            check_in_time=reference,
            status="active",
            staff_in_id=user.id,
        )
        db.add(session)
        db.commit()
        session_id = session.id
    finally:
        db.close()
    return engine, database_path, session_id, factory


def test_readiness_accepts_seeded_database_then_rejects_stuck_checking_out(
    tmp_path: Path,
):
    engine, database_path, session_id, factory = _seeded_database(
        tmp_path, "readiness.db"
    )
    try:
        # Control: DB vừa seed phải sẵn sàng.
        check_database_readiness(engine, deep=False)

        # Mô phỏng tiến trình chết ngay sau khi claim: `checking_out` bị COMMIT
        # và đọng lại. Readiness phải fail-closed thay vì cho hệ thống chạy tiếp.
        db = factory()
        try:
            assert crud_session.claim_session_for_checkout(db, session_id)
            db.commit()
        finally:
            db.close()

        with pytest.raises(RuntimeError, match="parking_sessions"):
            check_database_readiness(engine, deep=False)
    finally:
        engine.dispose()
    assert database_path.is_file()
