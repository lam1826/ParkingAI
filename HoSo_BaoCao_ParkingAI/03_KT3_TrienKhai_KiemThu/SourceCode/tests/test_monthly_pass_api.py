"""Regression test cho API vé tháng (/api/v1/monthly-passes).

Phủ các lỗi đã xác nhận trong đợt review:
- PUT một phần (chỉ start_date hoặc chỉ end_date) không được commit
  khoảng ngày sai (end_date < start_date) vào DB.
- Sau một request lỗi, GET danh sách vẫn phải hoạt động và DB không đổi.
- Response GET/POST/PUT dùng cùng một contract, có nhúng thông tin
  rút gọn vehicle/customer mà bảng frontend cần.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.parking_session import ParkingSession
from models.user import User
from models.vehicle import Vehicle
from services.auth_service import AuthService
from core.money import MAX_EXACT_VND


def make_headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


def _create_pass(db_session: Session, vehicle: Vehicle, customer: Customer,
                 start: datetime.date, end: datetime.date) -> MonthlyPass:
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=start,
        end_date=end,
        is_active=True,
    )
    db_session.add(monthly_pass)
    db_session.commit()
    db_session.refresh(monthly_pass)
    return monthly_pass


TODAY = datetime.date.today()


# Mốc cố định ở tương lai: các test overlap không được phụ thuộc
# "hôm nay" của máy chạy test hay business_today() trong production.
OVERLAP_BASE = datetime.date(2035, 1, 1)


def test_delete_used_monthly_pass_is_blocked_and_preserves_provenance(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    customer: Customer,
    parking_slot,
    # Chính sách admission: MỌI phiên active (kể cả có vé tháng) đều cần bảng
    # giá fallback đang hiệu lực tại check-in.
    price_config,
    business_reference_now,
):
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now,
        status="active",
        staff_in_id=test_user.id,
    )
    db_session.add(parking_session)
    db_session.commit()

    response = client.delete(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert "ngừng hoạt động" in response.json()["detail"].lower()
    db_session.expire_all()
    assert db_session.get(MonthlyPass, monthly_pass.id) is not None
    assert db_session.get(ParkingSession, parking_session.id).monthly_pass_id == monthly_pass.id


def test_used_monthly_pass_can_be_soft_deactivated_without_losing_provenance(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    customer: Customer,
    parking_slot,
    price_config,
    business_reference_now,
):
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now,
        status="active",
        staff_in_id=test_user.id,
    )
    db_session.add(parking_session)
    db_session.commit()

    response = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"is_active": False},
        headers=make_headers(test_user),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    db_session.expire_all()
    assert db_session.get(MonthlyPass, monthly_pass.id) is not None
    assert db_session.get(ParkingSession, parking_session.id).monthly_pass_id == monthly_pass.id


def test_used_monthly_pass_business_fields_are_immutable(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    customer: Customer,
    parking_slot,
    vehicle_type,
    price_config,
    business_reference_now,
):
    """A session FK is an audit snapshot; referenced pass facts cannot drift."""
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )
    monthly_pass.pass_code = "IMMUTABLE-PASS"
    monthly_pass.price = 500_000
    other_customer = Customer(full_name="Khách khác", phone_number="0909000002")
    db_session.add(other_customer)
    db_session.flush()
    other_vehicle = Vehicle(
        license_plate="51A-IMMUTABLE",
        vehicle_type_id=vehicle_type.id,
        customer_id=other_customer.id,
    )
    db_session.add(other_vehicle)
    db_session.flush()
    parking_session = ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now,
        status="active",
        staff_in_id=test_user.id,
    )
    db_session.add(parking_session)
    db_session.commit()
    snapshot = {
        field: getattr(monthly_pass, field)
        for field in (
            "customer_id",
            "vehicle_id",
            "pass_code",
            "price",
            "start_date",
            "end_date",
        )
    }
    changes = (
        {"customer_id": other_customer.id},
        {"vehicle_id": other_vehicle.id},
        {"pass_code": "CHANGED-PASS"},
        {"price": 600_000},
        {"start_date": (monthly_pass.start_date - datetime.timedelta(days=1)).isoformat()},
        {"end_date": (monthly_pass.end_date + datetime.timedelta(days=1)).isoformat()},
    )

    for payload in changes:
        response = client.put(
            f"/api/v1/monthly-passes/{monthly_pass.id}",
            json=payload,
            headers=make_headers(test_user),
        )
        assert response.status_code == 409, payload
        db_session.expire_all()
        persisted = db_session.get(MonthlyPass, monthly_pass.id)
        assert {
            field: getattr(persisted, field) for field in snapshot
        } == snapshot


def test_db_trigger_rejects_used_monthly_pass_history_rewrite(
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    customer: Customer,
    parking_slot,
    price_config,
    business_reference_now,
):
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )
    db_session.add(ParkingSession(
        vehicle_id=vehicle.id,
        parking_slot_id=parking_slot.id,
        monthly_pass_id=monthly_pass.id,
        check_in_time=business_reference_now,
        status="active",
        staff_in_id=test_user.id,
    ))
    db_session.commit()

    monthly_pass.price = 123_456
    with pytest.raises(IntegrityError, match="monthly pass history immutable"):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(MonthlyPass, monthly_pass.id).price == 0


@pytest.mark.parametrize("invalid_price", [1000.5, -1, MAX_EXACT_VND + 1])
def test_db_trigger_rejects_invalid_monthly_pass_price(
    db_session: Session,
    vehicle: Vehicle,
    customer: Customer,
    business_reference_now,
    invalid_price,
):
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )
    monthly_pass.price = invalid_price

    with pytest.raises(
        IntegrityError,
        match="monthly pass price must be nonnegative integer",
    ):
        db_session.commit()
    db_session.rollback()
    assert db_session.get(MonthlyPass, monthly_pass.id).price == 0


def test_db_trigger_rejects_invalid_monthly_pass_date_range(
    db_session: Session,
    vehicle: Vehicle,
    customer: Customer,
    business_reference_now,
):
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )
    monthly_pass.end_date = monthly_pass.start_date - datetime.timedelta(days=1)

    with pytest.raises(IntegrityError, match="monthly pass date range invalid"):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("not-a-date", "zzzz"),
        ("2026-1-2", "2026-1-3"),
        ("2026-02-30", "2026-03-01"),
        ("2025-02-29", "2025-03-01"),
        ("2026-01-01T00:00:00", "2026-01-02"),
        ("2026-01-01", "2026-01-02T00:00:00"),
        ("2026-09-01", "2026-08-31"),
        ("0000-01-01", "0000-01-02"),
        (20260801, 20260831),
    ],
)
def test_db_insert_rejects_noncanonical_or_invalid_monthly_pass_dates(
    db_session: Session,
    vehicle: Vehicle,
    customer: Customer,
    start_date,
    end_date,
):
    with pytest.raises(IntegrityError, match="monthly pass date range invalid"):
        db_session.execute(
            text(
                "INSERT INTO monthly_passes("
                "customer_id, vehicle_id, pass_code, price, start_date, "
                "end_date, is_active) VALUES "
                "(:customer_id, :vehicle_id, :pass_code, 0, "
                ":start_date, :end_date, 0)"
            ),
            {
                "customer_id": customer.id,
                "vehicle_id": vehicle.id,
                "pass_code": f"BAD-DATE-{start_date}",
                "start_date": start_date,
                "end_date": end_date,
            },
        )


def test_db_insert_accepts_canonical_valid_monthly_pass_dates(
    db_session: Session,
    vehicle: Vehicle,
    customer: Customer,
):
    db_session.execute(
        text(
            "INSERT INTO monthly_passes("
            "customer_id, vehicle_id, pass_code, price, start_date, "
            "end_date, is_active) VALUES "
            "(:customer_id, :vehicle_id, 'VALID-LEAP-DATE', 0, "
            "'2024-02-29', '2024-03-01', 0)"
        ),
        {"customer_id": customer.id, "vehicle_id": vehicle.id},
    )
    db_session.commit()

    stored_dates = db_session.execute(
        text(
            "SELECT start_date, end_date FROM monthly_passes "
            "WHERE pass_code = 'VALID-LEAP-DATE'"
        )
    ).one()
    assert stored_dates == ("2024-02-29", "2024-03-01")


@pytest.mark.parametrize(
    ("price", "start_date", "end_date", "message"),
    [
        (1000.5, "2026-08-01", "2026-08-31", "giá="),
        (-1, "2026-08-01", "2026-08-31", "giá="),
        (MAX_EXACT_VND + 1, "2026-08-01", "2026-08-31", "giá="),
        (0, "2026-09-01", "2026-08-31", "khoảng ngày="),
        (0, "not-a-date", "zzzz", "khoảng ngày="),
        (0, "2026-1-2", "2026-1-3", "khoảng ngày="),
        (0, "2026-02-30", "2026-03-01", "khoảng ngày="),
    ],
)
def test_migration_rejects_invalid_legacy_monthly_pass_contract(
    tmp_path,
    price,
    start_date,
    end_date,
    message,
):
    from database import run_sqlite_migrations

    database_path = tmp_path / f"legacy-pass-{abs(hash((price, start_date)))}.db"
    legacy_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE monthly_passes ("
            "id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, "
            "vehicle_id INTEGER NOT NULL, pass_code VARCHAR(50), price, "
            "start_date DATE NOT NULL, end_date DATE NOT NULL, "
            "is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO monthly_passes(id, customer_id, vehicle_id, pass_code, "
            "price, start_date, end_date, is_active) VALUES "
            "(1, 1, 1, 'LEGACY', ?, ?, ?, 1)",
            (price, start_date, end_date),
        )

    with pytest.raises(RuntimeError, match=message):
        run_sqlite_migrations(legacy_engine)


def test_delete_unused_monthly_pass_remains_available_for_data_cleanup(
    client: TestClient,
    db_session: Session,
    test_user: User,
    vehicle: Vehicle,
    customer: Customer,
    business_reference_now,
):
    monthly_pass = _create_pass(
        db_session,
        vehicle,
        customer,
        business_reference_now.date(),
        business_reference_now.date() + datetime.timedelta(days=30),
    )

    response = client.delete(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        headers=make_headers(test_user),
    )

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(MonthlyPass, monthly_pass.id) is None


def test_pytest_uses_isolated_database_engine():
    """Engine mặc định của application trong môi trường pytest PHẢI là
    database test in-memory — tuyệt đối không trỏ tới file DB thật nào
    trong workspace (main.py chạy migration + create_all ngay khi import)."""
    from database import engine

    url = str(engine.url)
    assert url == "sqlite:///:memory:"
    assert "parking.db" not in url


def test_create_rejects_active_pass_overlap_at_inclusive_boundary(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Hai khoảng active chạm nhau tại một ngày vẫn là giao nhau.

    Bản ghi có sẵn nằm xa trong tương lai để chứng minh contract
    phải so sánh [start_date, end_date], không được hỏi vé nào đang
    hiệu lực tại business_today().
    """
    existing_start = OVERLAP_BASE + datetime.timedelta(days=30)
    existing_end = existing_start + datetime.timedelta(days=10)
    existing = _create_pass(
        db_session, vehicle, customer, existing_start, existing_end
    )

    response = client.post(
        "/api/v1/monthly-passes",
        json={
            "customer_id": customer.id,
            "vehicle_id": vehicle.id,
            "pass_code": "NFC-OVERLAP-BOUNDARY",
            "price": 500000,
            "start_date": OVERLAP_BASE.isoformat(),
            "end_date": existing_start.isoformat(),
            "is_active": True,
        },
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert str(existing.id) in response.json()["detail"]
    assert db_session.query(MonthlyPass).count() == 1


def test_partial_update_rejects_merged_interval_overlap_and_keeps_db_unchanged(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """PUT chỉ end_date phải ghép với start_date hiện có trước
    khi kiểm tra overlap; chính record đang sửa không được tính là
    conflict, nhưng một record khác chạm ngày biên phải bị chặn.
    """
    target = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE + datetime.timedelta(days=10),
        OVERLAP_BASE + datetime.timedelta(days=20),
    )
    blocker = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE + datetime.timedelta(days=30),
        OVERLAP_BASE + datetime.timedelta(days=40),
    )
    original_end = target.end_date

    response = client.put(
        f"/api/v1/monthly-passes/{target.id}",
        json={"end_date": blocker.start_date.isoformat()},
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert str(blocker.id) in response.json()["detail"]
    db_session.refresh(target)
    assert target.end_date == original_end


def test_create_allows_disjoint_active_intervals_for_same_vehicle(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Hai vé active cùng xe được phép khi vé sau bắt đầu từ
    ngày kế tiếp sau end_date của vé trước (không giao nhau)."""
    existing = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE,
        OVERLAP_BASE + datetime.timedelta(days=10),
    )
    next_start = existing.end_date + datetime.timedelta(days=1)

    response = client.post(
        "/api/v1/monthly-passes",
        json={
            "customer_id": customer.id,
            "vehicle_id": vehicle.id,
            "pass_code": "NFC-DISJOINT",
            "price": 500000,
            "start_date": next_start.isoformat(),
            "end_date": (next_start + datetime.timedelta(days=10)).isoformat(),
            "is_active": True,
        },
        headers=make_headers(test_user),
    )

    assert response.status_code == 201
    assert db_session.query(MonthlyPass).count() == 2


def test_partial_update_allows_disjoint_interval_and_excludes_self(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """PUT partial hợp lệ không được xung đột với chính record;
    record khác kết thúc trước ngày bắt đầu mới vẫn rời nhau."""
    blocker = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE,
        OVERLAP_BASE + datetime.timedelta(days=10),
    )
    target = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE + datetime.timedelta(days=20),
        OVERLAP_BASE + datetime.timedelta(days=30),
    )
    new_start = blocker.end_date + datetime.timedelta(days=1)

    response = client.put(
        f"/api/v1/monthly-passes/{target.id}",
        json={"start_date": new_start.isoformat()},
        headers=make_headers(test_user),
    )

    assert response.status_code == 200
    assert response.json()["start_date"] == new_start.isoformat()


def test_db_trigger_blocks_overlapping_active_pass_bypassing_api(
    db_session: Session,
    vehicle: Vehicle,
    customer: Customer,
):
    """Backstop chặn race/đường ghi trực tiếp không đi qua router."""
    existing = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE,
        OVERLAP_BASE + datetime.timedelta(days=10),
    )
    db_session.add(
        MonthlyPass(
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            pass_code="DIRECT-OVERLAP",
            price=500_000,
            start_date=existing.end_date,
            end_date=existing.end_date + datetime.timedelta(days=5),
            is_active=True,
        )
    )

    with pytest.raises(IntegrityError, match="monthly pass interval overlap"):
        db_session.commit()
    db_session.rollback()
    assert db_session.query(MonthlyPass).count() == 1

    db_session.add(
        MonthlyPass(
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            pass_code="DIRECT-DISJOINT",
            price=500_000,
            start_date=existing.end_date + datetime.timedelta(days=1),
            end_date=existing.end_date + datetime.timedelta(days=5),
            is_active=True,
        )
    )
    db_session.commit()
    assert db_session.query(MonthlyPass).count() == 2


def test_db_trigger_blocks_direct_update_into_overlapping_interval(
    db_session: Session,
    vehicle: Vehicle,
    customer: Customer,
):
    """Backstop UPDATE phải bảo vệ cả partial/direct ORM write."""
    first = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE,
        OVERLAP_BASE + datetime.timedelta(days=10),
    )
    second = _create_pass(
        db_session,
        vehicle,
        customer,
        OVERLAP_BASE + datetime.timedelta(days=20),
        OVERLAP_BASE + datetime.timedelta(days=30),
    )
    original_start = second.start_date
    second.start_date = first.end_date

    with pytest.raises(IntegrityError, match="monthly pass interval overlap"):
        db_session.commit()
    db_session.rollback()
    db_session.refresh(second)
    assert second.start_date == original_start


def test_migration_fails_loudly_on_legacy_monthly_pass_overlap(tmp_path):
    from sqlalchemy import create_engine

    from database import run_sqlite_migrations

    db_file = tmp_path / "legacy-overlapping-passes.db"
    legacy_engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE monthly_passes ("
            "id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, "
            "vehicle_id INTEGER NOT NULL, pass_code VARCHAR(50), "
            "price INTEGER NOT NULL DEFAULT 0, start_date DATE NOT NULL, "
            "end_date DATE NOT NULL, is_active BOOLEAN NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO monthly_passes "
            "(id, customer_id, vehicle_id, start_date, end_date, is_active) "
            "VALUES (1, 1, 9, '2035-01-01', '2035-01-31', 1), "
            "(2, 1, 9, '2035-01-31', '2035-02-28', 1)"
        )

    with pytest.raises(RuntimeError, match=r"chồng.*1.*2|1.*2.*chồng"):
        run_sqlite_migrations(legacy_engine)

    with legacy_engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM monthly_passes"
        ).scalar_one() == 2
        trigger_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'trg_monthly_passes_no_overlap_%'"
        ).scalar_one()
    assert trigger_count == 0
    legacy_engine.dispose()


def test_update_only_start_date_after_end_rejected(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """PUT chỉ start_date thành ngày SAU end_date hiện có -> 422, DB không đổi."""
    monthly_pass = _create_pass(
        db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10)
    )
    original_start = monthly_pass.start_date

    bad_start = (TODAY + datetime.timedelta(days=20)).isoformat()
    response = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"start_date": bad_start},
        headers=make_headers(test_user),
    )

    assert response.status_code == 422
    db_session.refresh(monthly_pass)
    assert monthly_pass.start_date == original_start
    assert monthly_pass.end_date >= monthly_pass.start_date


def test_update_only_end_date_before_start_rejected(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """PUT chỉ end_date thành ngày TRƯỚC start_date hiện có -> 422, DB không đổi."""
    start = TODAY + datetime.timedelta(days=5)
    monthly_pass = _create_pass(
        db_session, vehicle, customer, start, start + datetime.timedelta(days=30)
    )
    original_end = monthly_pass.end_date

    bad_end = (start - datetime.timedelta(days=1)).isoformat()
    response = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"end_date": bad_end},
        headers=make_headers(test_user),
    )

    assert response.status_code == 422
    db_session.refresh(monthly_pass)
    assert monthly_pass.end_date == original_end


def test_update_valid_dates_succeeds(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Gia hạn hợp lệ (chỉ gửi end_date mới, vẫn >= start_date) -> 200."""
    monthly_pass = _create_pass(
        db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10)
    )
    new_end = (TODAY + datetime.timedelta(days=40)).isoformat()

    response = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"end_date": new_end},
        headers=make_headers(test_user),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["end_date"] == new_end
    db_session.refresh(monthly_pass)
    assert monthly_pass.end_date.isoformat() == new_end


def test_list_still_works_after_failed_update(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Request lỗi không được 'đầu độc' GET danh sách cho các vé khác."""
    monthly_pass = _create_pass(
        db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10)
    )
    headers = make_headers(test_user)

    bad_start = (TODAY + datetime.timedelta(days=99)).isoformat()
    failed = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"start_date": bad_start},
        headers=headers,
    )
    assert failed.status_code == 422

    listing = client.get("/api/v1/monthly-passes", headers=headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["id"] == monthly_pass.id


def test_response_contract_includes_vehicle_and_customer(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """GET/POST/PUT phải trả cùng contract: nhúng vehicle.license_plate và
    customer.full_name mà bảng frontend hiển thị."""
    headers = make_headers(test_user)
    payload = {
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "pass_code": "NFC-CONTRACT-01",
        "price": 500000,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + datetime.timedelta(days=30)).isoformat(),
        "is_active": True,
    }

    created = client.post("/api/v1/monthly-passes", json=payload, headers=headers)
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["vehicle"]["license_plate"] == vehicle.license_plate
    assert created_body["customer"]["full_name"] == customer.full_name

    listing = client.get("/api/v1/monthly-passes", headers=headers)
    assert listing.status_code == 200
    row = listing.json()[0]
    assert row["vehicle"]["license_plate"] == vehicle.license_plate
    assert row["customer"]["full_name"] == customer.full_name
    assert row["customer"]["phone_number"] == customer.phone_number

    updated = client.put(
        f"/api/v1/monthly-passes/{created_body['id']}",
        json={"end_date": (TODAY + datetime.timedelta(days=60)).isoformat()},
        headers=headers,
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    # POST/PUT/GET có cùng tập key contract
    assert set(updated_body.keys()) == set(created_body.keys()) == set(row.keys())
    assert updated_body["vehicle"]["license_plate"] == vehicle.license_plate


def test_list_survives_legacy_corrupted_row(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Bản ghi cũ lỡ sai khoảng ngày (tạo trước khi có validation) không được
    làm 500 toàn bộ GET danh sách — response schema không chạy lại validator."""
    # Mô phỏng DB legacy trước khi có trigger date-range. DB mới chặn đường
    # ghi này; rollout fail-loudly nếu gặp bản ghi như vậy.
    db_session.execute(text("DROP TRIGGER trg_monthly_passes_date_range_insert"))
    corrupted = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        start_date=TODAY + datetime.timedelta(days=10),
        end_date=TODAY,  # end < start
        is_active=True,
    )
    db_session.add(corrupted)
    db_session.commit()

    response = client.get("/api/v1/monthly-passes", headers=make_headers(test_user))
    assert response.status_code == 200
    assert len(response.json()) == 1


# ---------------------------------------------------------------------------
# Contract pass_code / price (đợt sửa E)
# ---------------------------------------------------------------------------


def test_create_persists_pass_code_and_price(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """POST không được silent-drop: pass_code (đã chuẩn hóa) và price phải
    được lưu vào DB và trả lại trong response."""
    payload = {
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "pass_code": "  nfc-abc-01  ",  # có khoảng trắng + chữ thường
        "price": 750000,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + datetime.timedelta(days=30)).isoformat(),
    }

    response = client.post(
        "/api/v1/monthly-passes", json=payload, headers=make_headers(test_user)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["pass_code"] == "NFC-ABC-01"  # trim + upper
    assert body["price"] == 750000

    stored = db_session.get(MonthlyPass, body["id"])
    assert stored.pass_code == "NFC-ABC-01"
    assert stored.price == 750000


def test_create_requires_pass_code(
    client: TestClient, test_user: User, vehicle: Vehicle, customer: Customer,
):
    """pass_code là bắt buộc — thiếu phải trả 422, không được lặng lẽ chấp nhận."""
    payload = {
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "price": 500000,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + datetime.timedelta(days=30)).isoformat(),
    }
    response = client.post(
        "/api/v1/monthly-passes", json=payload, headers=make_headers(test_user)
    )
    assert response.status_code == 422


def test_create_rejects_unknown_fields(
    client: TestClient, test_user: User, vehicle: Vehicle, customer: Customer,
):
    """extra='forbid': field lạ trong payload phải bị từ chối (422),
    không còn bị Pydantic âm thầm loại bỏ."""
    payload = {
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "pass_code": "NFC-UNKNOWN-01",
        "price": 500000,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + datetime.timedelta(days=30)).isoformat(),
        "totally_unknown_field": "x",
    }
    response = client.post(
        "/api/v1/monthly-passes", json=payload, headers=make_headers(test_user)
    )
    assert response.status_code == 422


def test_duplicate_pass_code_rejected(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """pass_code trùng (kể cả khác hoa/thường, thừa khoảng trắng) -> 400."""
    headers = make_headers(test_user)
    base_payload = {
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "pass_code": "NFC-DUP-01",
        "price": 500000,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + datetime.timedelta(days=30)).isoformat(),
        "is_active": False,  # vé 1 không active để không vướng check chồng vé
    }
    first = client.post("/api/v1/monthly-passes", json=base_payload, headers=headers)
    assert first.status_code == 201

    duplicated = client.post(
        "/api/v1/monthly-passes",
        json={**base_payload, "pass_code": " nfc-dup-01 "},
        headers=headers,
    )
    assert duplicated.status_code == 400
    assert "Mã thẻ" in duplicated.json()["detail"]


def test_negative_price_rejected(
    client: TestClient, test_user: User, vehicle: Vehicle, customer: Customer,
):
    payload = {
        "customer_id": customer.id,
        "vehicle_id": vehicle.id,
        "pass_code": "NFC-NEG-01",
        "price": -1,
        "start_date": TODAY.isoformat(),
        "end_date": (TODAY + datetime.timedelta(days=30)).isoformat(),
    }
    response = client.post(
        "/api/v1/monthly-passes", json=payload, headers=make_headers(test_user)
    )
    assert response.status_code == 422


def test_update_pass_code_checks_duplicate(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """PUT đổi pass_code sang mã đã thuộc vé khác -> 400; đổi sang mã mới -> 200."""
    headers = make_headers(test_user)
    pass_a = _create_pass(db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10))
    pass_a.pass_code = "NFC-A"
    pass_b = MonthlyPass(
        customer_id=customer.id, vehicle_id=vehicle.id,
        start_date=TODAY, end_date=TODAY + datetime.timedelta(days=10),
        is_active=False, pass_code="NFC-B",
    )
    db_session.add(pass_b)
    db_session.commit()

    conflict = client.put(
        f"/api/v1/monthly-passes/{pass_b.id}",
        json={"pass_code": "nfc-a"},
        headers=headers,
    )
    assert conflict.status_code == 400

    renamed = client.put(
        f"/api/v1/monthly-passes/{pass_b.id}",
        json={"pass_code": "NFC-B2"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["pass_code"] == "NFC-B2"


def test_legacy_row_without_pass_code_serializes_safely(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Bản ghi cũ (pass_code NULL, price backfill 0) phải serialize an toàn."""
    legacy = _create_pass(
        db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10)
    )
    assert legacy.pass_code is None

    response = client.get("/api/v1/monthly-passes", headers=make_headers(test_user))
    assert response.status_code == 200
    row = response.json()[0]
    assert row["pass_code"] is None
    assert row["price"] == 0


# ---------------------------------------------------------------------------
# Hotfix 1.1: từ chối explicit null trong MonthlyPassUpdate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    ["customer_id", "vehicle_id", "pass_code", "price", "start_date", "end_date", "is_active"],
)
def test_update_rejects_explicit_null(
    field_name: str,
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Key có mặt với giá trị null -> 422 (chỉ rõ field), DB giữ nguyên,
    GET danh sách vẫn hoạt động."""
    monthly_pass = _create_pass(
        db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10)
    )
    monthly_pass.pass_code = "NFC-NULLTEST"
    monthly_pass.price = 123000
    db_session.commit()
    headers = make_headers(test_user)

    snapshot = {
        "customer_id": monthly_pass.customer_id,
        "vehicle_id": monthly_pass.vehicle_id,
        "pass_code": monthly_pass.pass_code,
        "price": monthly_pass.price,
        "start_date": monthly_pass.start_date,
        "end_date": monthly_pass.end_date,
        "is_active": monthly_pass.is_active,
    }

    response = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={field_name: None},
        headers=headers,
    )

    assert response.status_code == 422
    # Thông báo lỗi phải chỉ rõ field không được phép null
    assert field_name in str(response.json()["detail"])

    db_session.refresh(monthly_pass)
    for key, value in snapshot.items():
        assert getattr(monthly_pass, key) == value

    listing = client.get("/api/v1/monthly-passes", headers=headers)
    assert listing.status_code == 200


def test_partial_update_single_fields_still_work(
    client: TestClient, db_session: Session, test_user: User,
    vehicle: Vehicle, customer: Customer,
):
    """Partial update hợp lệ không bắt buộc gửi lại toàn bộ object:
    chỉ price, rồi chỉ pass_code (end_date-only đã có test riêng ở trên)."""
    monthly_pass = _create_pass(
        db_session, vehicle, customer, TODAY, TODAY + datetime.timedelta(days=10)
    )
    headers = make_headers(test_user)

    only_price = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"price": 990000},
        headers=headers,
    )
    assert only_price.status_code == 200
    assert only_price.json()["price"] == 990000

    only_code = client.put(
        f"/api/v1/monthly-passes/{monthly_pass.id}",
        json={"pass_code": "nfc-solo"},
        headers=headers,
    )
    assert only_code.status_code == 200
    body = only_code.json()
    assert body["pass_code"] == "NFC-SOLO"
    assert body["price"] == 990000  # giá đổi ở bước trước vẫn giữ nguyên

    db_session.refresh(monthly_pass)
    assert monthly_pass.price == 990000
    assert monthly_pass.pass_code == "NFC-SOLO"


def test_sqlite_migration_adds_columns_to_legacy_schema():
    """run_sqlite_migrations phải nâng cấp DB schema CŨ (chưa có pass_code/price):
    thêm cột, backfill price=0 và tạo unique index — idempotent khi chạy lại."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from database import run_sqlite_migrations

    legacy_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with legacy_engine.begin() as conn:
        # Bảng theo schema cũ, kèm 1 bản ghi có sẵn
        conn.exec_driver_sql(
            "CREATE TABLE monthly_passes ("
            " id INTEGER PRIMARY KEY,"
            " customer_id INTEGER, vehicle_id INTEGER,"
            " start_date DATE, end_date DATE, is_active BOOLEAN,"
            " created_at DATETIME, updated_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO monthly_passes (customer_id, vehicle_id, start_date, end_date, is_active)"
            " VALUES (1, 1, '2026-01-01', '2026-02-01', 1)"
        )

    run_sqlite_migrations(legacy_engine)
    run_sqlite_migrations(legacy_engine)  # idempotent — chạy lại không lỗi

    with legacy_engine.connect() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(monthly_passes)")}
        assert {"pass_code", "price"} <= columns

        legacy_row = conn.exec_driver_sql(
            "SELECT pass_code, price FROM monthly_passes WHERE id = 1"
        ).fetchone()
        assert legacy_row[0] is None  # bản ghi cũ: pass_code NULL
        assert legacy_row[1] == 0     # backfill price = 0

        indexes = {row[1] for row in conn.exec_driver_sql("PRAGMA index_list(monthly_passes)")}
        assert "ix_monthly_passes_pass_code" in indexes
