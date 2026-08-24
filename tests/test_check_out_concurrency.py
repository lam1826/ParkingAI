"""Regression test Đợt 4: server-authoritative check-out + race condition.

Nguyên tắc:
- Concurrency dùng SQLite FILE TẠM (tmp_path) + Session riêng mỗi worker;
  không dùng in-memory StaticPool để giả lập concurrency.
- Interleaving điều phối bằng threading.Barrier gắn vào before_cursor_execute,
  dừng mỗi thread ngay TRƯỚC UPDATE đầu tiên của nó (sau khi cả hai đã SELECT
  thấy session active) — không sleep, không vòng lặp xác suất.
- Số lần calculate_fee được đếm bằng wrapper trên ParkingService.
- Server time freeze bằng monkeypatch crud.parking_session.server_now.
"""

import datetime
import threading

import bcrypt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from crud import parking_session as crud_session_module
from database import Base, run_sqlite_migrations
from models.customer import Customer
from models.monthly_pass import MonthlyPass
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


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    token = AuthService().create_access_token(
        user_id=test_user.id, username=test_user.username, role=str(test_user.role)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fee_counter(monkeypatch):
    """Đếm số lần calculate_fee thực sự chạy."""
    calls = {"n": 0}
    original = ParkingService.calculate_fee

    def counting(self, *args, **kwargs):
        calls["n"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ParkingService, "calculate_fee", counting)
    return calls


# ===========================================================================
# 1. Client-controlled fields -> 422, DB không đổi (qua route thật/TestClient)
# ===========================================================================


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("check_out_time", "2026-01-01T00:00:01"),
        ("parking_fee", 0),
        ("status", "completed"),
        ("staff_out_id", 999),
        ("bogus_field", 1),
    ],
)
def test_put_rejects_client_controlled_fields(
    field_name, value,
    client, auth_headers, db_session, parking_session, parking_slot, price_config,
):
    response = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={field_name: value},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert field_name in str(response.json()["detail"])

    db_session.refresh(parking_session)
    db_session.refresh(parking_slot)
    assert parking_session.status == "active"
    assert parking_session.check_out_time is None
    assert parking_session.parking_fee is None
    assert parking_session.staff_out_id is None
    assert parking_slot.is_occupied is True


@pytest.mark.parametrize(
    "extra_payload",
    [{"check_out_time": "2026-01-01T00:00:01"}, {"parking_fee": 0}],
)
def test_post_rejects_extra_fields(
    extra_payload,
    client, auth_headers, db_session, vehicle, parking_session, parking_slot, price_config,
):
    response = client.post(
        "/parking/check-out",
        json={"license_plate": vehicle.license_plate, **extra_payload},
        headers=auth_headers,
    )

    assert response.status_code == 422
    field = next(iter(extra_payload))
    assert field in str(response.json()["detail"])

    db_session.refresh(parking_session)
    db_session.refresh(parking_slot)
    assert parking_session.status == "active"
    assert parking_slot.is_occupied is True


# ===========================================================================
# 2. Server time: freeze và kiểm tra phí + thời gian persisted
# ===========================================================================


def test_server_time_is_authoritative(
    client, auth_headers, db_session, parking_session, price_config, monkeypatch,
):
    frozen = parking_session.check_in_time + datetime.timedelta(hours=2)
    monkeypatch.setattr(crud_session_module, "server_now", lambda: frozen)

    response = client.put(
        f"/api/v1/parking-sessions/{parking_session.id}/check-out",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["check_out_time"] == frozen.isoformat()
    # Đúng 2 giờ (không lệch giây nào) -> phí = 2 x đơn giá theo server clock
    assert data["parking_fee"] == price_config.price * 2

    db_session.refresh(parking_session)
    assert parking_session.check_out_time == frozen


def test_post_server_time_is_authoritative(
    client, auth_headers, db_session, vehicle, parking_session, price_config, monkeypatch,
):
    frozen = parking_session.check_in_time + datetime.timedelta(hours=3)
    monkeypatch.setattr(crud_session_module, "server_now", lambda: frozen)

    response = client.post(
        "/parking/check-out",
        json={"license_plate": vehicle.license_plate},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["parking_fee"] == price_config.price * 3
    db_session.refresh(parking_session)
    assert parking_session.check_out_time == frozen


# ===========================================================================
# 3. Idempotent PUT tuần tự (x3), phí tính đúng một lần
# ===========================================================================


def test_sequential_put_is_idempotent_and_fee_computed_once(
    client, auth_headers, db_session, parking_session, parking_slot,
    price_config, fee_counter,
):
    responses = [
        client.put(
            f"/api/v1/parking-sessions/{parking_session.id}/check-out",
            json={},
            headers=auth_headers,
        )
        for _ in range(3)
    ]

    assert [r.status_code for r in responses] == [200, 200, 200]
    first = responses[0].json()
    for later in responses[1:]:
        data = later.json()
        assert data["parking_fee"] == first["parking_fee"]
        assert data["check_out_time"] == first["check_out_time"]
        assert data["status"] == "completed"

    assert fee_counter["n"] == 1, "calculate_fee chỉ được chạy đúng một lần"

    db_session.refresh(parking_session)
    db_session.refresh(parking_slot)
    assert parking_session.status == "completed"
    assert parking_slot.is_occupied is False


# ===========================================================================
# Môi trường concurrency: DB file tạm + Session riêng mỗi worker
# ===========================================================================


class CheckoutEnv:
    def __init__(self, engine, session_factory, ids):
        self.engine = engine
        self.Session = session_factory
        self.__dict__.update(ids)

    def run_pair(self, fn_a, fn_b, sync_on=("UPDATE PARKING_SESSIONS",)):
        barrier = threading.Barrier(2)
        local = threading.local()

        @event.listens_for(self.engine, "before_cursor_execute")
        def sync(conn, cursor, statement, params, ctx, many):
            if getattr(local, "synced", False):
                return
            if any(statement.lstrip().upper().startswith(p) for p in sync_on):
                local.synced = True
                try:
                    barrier.wait(timeout=15)
                except threading.BrokenBarrierError:
                    pass

        results = {}

        def wrap(idx, fn):
            try:
                results[idx] = fn()
            except HTTPException as exc:
                results[idx] = ("HTTP", exc.status_code, str(exc.detail))
            except Exception as exc:  # noqa: BLE001
                results[idx] = ("EXC", type(exc).__name__, str(exc)[:200])
            finally:
                barrier.abort()

        threads = [
            threading.Thread(target=wrap, args=(0, fn_a)),
            threading.Thread(target=wrap, args=(1, fn_b)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=40)
        assert not any(t.is_alive() for t in threads), "Thread treo"
        event.remove(self.engine, "before_cursor_execute", sync)
        return results[0], results[1]

    def session_state(self, session_id):
        db = self.Session()
        try:
            s = db.get(ParkingSession, session_id)
            slot = db.get(ParkingSlot, self.slot_id)
            return {
                "status": s.status,
                "fee": s.parking_fee,
                "out_time": s.check_out_time,
                "staff_out": s.staff_out_id,
                "slot_occupied": slot.is_occupied,
            }
        finally:
            db.close()


@pytest.fixture()
def env(tmp_path):
    db_file = tmp_path / "checkout_race.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db = Session()
    role = Role(name="staff")
    db.add(role)
    db.commit()
    staff_a = User(username="co_staff_a", full_name="A", role_id=role.id,
                   password_hash=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode(),
                   is_active=True)
    staff_b = User(username="co_staff_b", full_name="B", role_id=role.id,
                   password_hash=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode(),
                   is_active=True)
    vt = VehicleType(name="Ô tô co", description="t")
    zone = Zone(name="Khu CO", capacity=10, is_active=True)
    db.add_all([staff_a, staff_b, vt, zone])
    db.commit()
    slot = ParkingSlot(zone_id=zone.id, vehicle_type_id=vt.id, slot_name="CO-1",
                       is_occupied=True, is_active=True)
    price = PriceConfig(vehicle_type_id=vt.id, ticket_type="HOURLY", price=25000.0,
                        effective_date=datetime.date.today() - datetime.timedelta(days=1),
                        is_active=True)
    vehicle = Vehicle(license_plate="80A-00001", vehicle_type_id=vt.id)
    db.add_all([slot, price, vehicle])
    db.commit()
    session = ParkingSession(
        vehicle_id=vehicle.id, parking_slot_id=slot.id,
        check_in_time=datetime.datetime.now() - datetime.timedelta(hours=3),
        status="active", staff_in_id=staff_a.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    ids = {
        "staff_a": staff_a.id, "staff_b": staff_b.id, "vt_id": vt.id,
        "slot_id": slot.id, "vehicle_id": vehicle.id, "plate": "80A-00001",
        "session_id": session.id, "price_id": price.id,
    }
    db.close()

    yield CheckoutEnv(engine, Session, ids)
    engine.dispose()


def _post_checkout(env, staff_id):
    def run():
        db = env.Session()
        try:
            r = ParkingService(db).check_out(license_plate=env.plate, staff_id=staff_id)
            return ("OK", 200, r["parking_fee"], r["check_out_time"], staff_id)
        finally:
            db.close()
    return run


def _put_checkout(env, staff_id):
    from routers.parking_session import check_out_vehicle

    def run():
        db = env.Session()
        try:
            user = db.get(User, staff_id)
            res = check_out_vehicle(id=env.session_id, session_in=None,
                                    db=db, current_user=user)
            return ("OK", 200, res.parking_fee, res.check_out_time, staff_id)
        finally:
            db.close()
    return run


# ===========================================================================
# 4. Concurrent PUT cùng session (hai nhân viên khác nhau)
# ===========================================================================


def test_concurrent_put_single_transition_and_idempotent_results(env, fee_counter):
    a, b = env.run_pair(_put_checkout(env, env.staff_a), _put_checkout(env, env.staff_b))

    # Cả hai phải 200 theo contract idempotent
    assert a[1] == 200 and b[1] == 200, f"A={a} B={b}"
    # Phí chỉ được tính đúng MỘT lần
    assert fee_counter["n"] == 1, f"calculate_fee chạy {fee_counter['n']} lần"
    # Hai response trả cùng một dữ liệu persisted (loser không ghi đè)
    assert a[2] == b[2], "parking_fee hai response phải giống nhau"
    assert a[3] == b[3], "check_out_time hai response phải giống nhau"

    state = env.session_state(env.session_id)
    assert state["status"] == "completed"
    assert state["fee"] == a[2]
    assert state["out_time"] == a[3]
    # staff_out_id thuộc về đúng MỘT trong hai nhân viên (transaction thắng)
    assert state["staff_out"] in (env.staff_a, env.staff_b)
    assert state["slot_occupied"] is False


# ===========================================================================
# 5. Concurrent POST cùng biển số
# ===========================================================================


def test_concurrent_post_one_winner_one_conflict(env, fee_counter):
    a, b = env.run_pair(_post_checkout(env, env.staff_a), _post_checkout(env, env.staff_b))

    statuses = sorted([a[1], b[1]])
    assert statuses == [200, 409], f"A={a} B={b}"
    assert fee_counter["n"] == 1, f"calculate_fee chạy {fee_counter['n']} lần"

    # Không lộ raw SQL trong thông báo lỗi của loser
    loser = a if a[1] == 409 else b
    assert "SQL" not in str(loser[2]) and "sqlite3" not in str(loser[2])

    winner = a if a[1] == 200 else b
    state = env.session_state(env.session_id)
    assert state["status"] == "completed"
    assert state["fee"] == winner[2]
    assert state["out_time"] == winner[3]
    # Audit thuộc transaction thắng, không bị loser ghi đè
    assert state["staff_out"] == winner[4]
    assert state["slot_occupied"] is False


# ===========================================================================
# 6. Rollback sau atomic claim
# ===========================================================================


def test_rollback_when_no_price_config(env):
    """calculate_fee 404 (không bảng giá) SAU khi claim -> session trở lại
    active, slot vẫn occupied, retry thành công sau khi có bảng giá."""
    db = env.Session()
    price = db.get(PriceConfig, env.price_id)
    price.is_active = False
    db.commit()
    db.close()

    with pytest.raises(HTTPException) as exc_info:
        _post_checkout(env, env.staff_a)()
    assert exc_info.value.status_code == 404

    state = env.session_state(env.session_id)
    assert state["status"] == "active", "Session phải trở lại active sau rollback"
    assert state["fee"] is None
    assert state["out_time"] is None
    assert state["staff_out"] is None
    assert state["slot_occupied"] is True

    # Bỏ nguyên nhân lỗi -> retry phải thành công
    db = env.Session()
    db.get(PriceConfig, env.price_id).is_active = True
    db.commit()
    db.close()

    result = _post_checkout(env, env.staff_a)()
    assert result[1] == 200
    assert env.session_state(env.session_id)["status"] == "completed"


def test_rollback_when_slot_release_fails(env):
    """Ép UPDATE parking_slots (giải phóng slot) thất bại sau claim + tính phí
    -> toàn bộ transaction rollback, session vẫn active, có thể retry."""
    fail_once = {"armed": True}

    @event.listens_for(env.engine, "before_cursor_execute")
    def break_slot_update(conn, cursor, statement, params, ctx, many):
        if fail_once["armed"] and statement.lstrip().upper().startswith(
            "UPDATE PARKING_SLOTS"
        ):
            fail_once["armed"] = False
            raise OperationalError("forced", {}, Exception("ép lỗi UPDATE slot"))

    try:
        with pytest.raises(HTTPException) as exc_info:
            _post_checkout(env, env.staff_a)()
        assert exc_info.value.status_code == 500
        assert "sqlite3" not in str(exc_info.value.detail)
    finally:
        event.remove(env.engine, "before_cursor_execute", break_slot_update)

    state = env.session_state(env.session_id)
    assert state["status"] == "active"
    assert state["fee"] is None
    assert state["staff_out"] is None
    assert state["slot_occupied"] is True

    retry = _post_checkout(env, env.staff_a)()
    assert retry[1] == 200
    assert env.session_state(env.session_id)["slot_occupied"] is False


# ===========================================================================
# 7. Session không gắn slot + monthly pass (không regression nghiệp vụ)
# ===========================================================================


def test_checkout_session_without_slot(env):
    db = env.Session()
    vehicle = Vehicle(license_plate="80B-00002", vehicle_type_id=env.vt_id)
    db.add(vehicle)
    db.commit()
    session = ParkingSession(
        vehicle_id=vehicle.id, parking_slot_id=None,
        check_in_time=datetime.datetime.now() - datetime.timedelta(hours=1),
        status="active", staff_in_id=env.staff_a,
    )
    db.add(session)
    db.commit()
    sid = session.id
    db.close()

    db = env.Session()
    try:
        result = ParkingService(db).check_out(
            license_plate="80B-00002", staff_id=env.staff_a
        )
    finally:
        db.close()
    assert result["status"] == "completed"
    assert result["parking_fee"] > 0

    db = env.Session()
    assert db.get(ParkingSession, sid).status == "completed"
    db.close()


def test_checkout_monthly_pass_still_free_via_put(
    client, auth_headers, db_session, customer, vehicle_type,
    parking_slot, test_user,
):
    vehicle = Vehicle(license_plate="80C-PASS1", vehicle_type_id=vehicle_type.id,
                      customer_id=customer.id)
    db_session.add(vehicle)
    db_session.commit()
    db_session.add(MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=datetime.date.today() - datetime.timedelta(days=5),
        end_date=datetime.date.today() + datetime.timedelta(days=25),
        is_active=True,
    ))
    session = ParkingSession(
        vehicle_id=vehicle.id, parking_slot_id=parking_slot.id,
        check_in_time=datetime.datetime.now() - datetime.timedelta(hours=2),
        status="active", staff_in_id=test_user.id,
    )
    parking_slot.is_occupied = True
    db_session.add(session)
    db_session.commit()

    response = client.put(
        f"/api/v1/parking-sessions/{session.id}/check-out",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["parking_fee"] == 0.0
