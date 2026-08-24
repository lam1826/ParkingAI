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
from sqlalchemy.orm import Session

from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.user import User
from models.vehicle import Vehicle
from services.auth_service import AuthService


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


def test_pytest_uses_isolated_database_engine():
    """Engine mặc định của application trong môi trường pytest PHẢI là
    database test in-memory — tuyệt đối không trỏ tới file DB thật nào
    trong workspace (main.py chạy migration + create_all ngay khi import)."""
    from database import engine

    url = str(engine.url)
    assert url == "sqlite:///:memory:"
    assert "parking.db" not in url


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
    # Chèn thẳng qua ORM để mô phỏng dữ liệu hỏng có sẵn trong DB cũ
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
