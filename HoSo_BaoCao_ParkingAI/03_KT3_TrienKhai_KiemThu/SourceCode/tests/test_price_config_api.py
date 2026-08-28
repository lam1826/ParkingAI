"""Regression test cho API bảng giá (/api/v1/price-configs).

Phủ cụm lỗi bảng giá của đợt review:
- P1-05: PUT phải validate TRẠNG THÁI SAU MERGE — một bảng giá đang active
  đổi vehicle_type_id sang loại xe đã có bảng giá active khác phải bị chặn
  409, dù payload không gửi is_active hay gửi is_active=true không đổi.
- P1-04: khi dữ liệu đã hỏng sẵn (hai bảng giá active cùng loại xe),
  POST/PUT phải trả 409 rõ ràng chứ không ném MultipleResultsFound -> 500.
- Explicit null trong partial update bị từ chối 422.
- Request lỗi không được thay đổi DB.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Integer, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.price_config import PriceConfig
from models.user import User
from models.vehicle_type import VehicleType
from services.auth_service import AuthService
from core.money import MAX_EXACT_VND

TODAY = datetime.date.today()


def make_headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


def _make_vehicle_type(db: Session, name: str) -> VehicleType:
    v_type = VehicleType(name=name, description=f"Loại xe test {name}")
    db.add(v_type)
    db.commit()
    db.refresh(v_type)
    return v_type


def _make_config(
    db: Session,
    vehicle_type_id: int,
    *,
    is_active: bool,
    ticket_type: str = "HOURLY",
    price: int = 20000,
    effective_date: datetime.date = TODAY,
) -> PriceConfig:
    config = PriceConfig(
        vehicle_type_id=vehicle_type_id,
        ticket_type=ticket_type,
        price=price,
        effective_date=effective_date,
        is_active=is_active,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _snapshot(config: PriceConfig) -> dict:
    return {
        "vehicle_type_id": config.vehicle_type_id,
        "ticket_type": config.ticket_type,
        "price": config.price,
        "effective_date": config.effective_date,
        "is_active": config.is_active,
    }


def _payload(vehicle_type_id: int, *, is_active: bool = True) -> dict:
    return {
        "vehicle_type_id": vehicle_type_id,
        "ticket_type": "HOURLY",
        "price": 30000,
        "effective_date": TODAY.isoformat(),
        "is_active": is_active,
    }


def _count_active(db: Session, vehicle_type_id: int) -> int:
    return (
        db.query(PriceConfig)
        .filter(
            PriceConfig.vehicle_type_id == vehicle_type_id,
            PriceConfig.is_active == True,  # noqa: E712
        )
        .count()
    )


# ---------------------------------------------------------------------------
# POST: bất biến một-active-mỗi-loại-xe
# ---------------------------------------------------------------------------


def test_post_second_active_same_type_returns_409(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    response = client.post(
        "/api/v1/price-configs",
        json=_payload(vehicle_type.id),
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert str(price_config.id) in response.json()["detail"]
    assert _count_active(db_session, vehicle_type.id) == 1


def test_post_inactive_same_type_allowed_multiple(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    headers = make_headers(test_user)
    for _ in range(2):
        response = client.post(
            "/api/v1/price-configs",
            json=_payload(vehicle_type.id, is_active=False),
            headers=headers,
        )
        assert response.status_code == 201

    assert _count_active(db_session, vehicle_type.id) == 1


def test_post_active_for_other_type_ok(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    other_type = _make_vehicle_type(db_session, "Xe máy")

    response = client.post(
        "/api/v1/price-configs",
        json=_payload(other_type.id),
        headers=make_headers(test_user),
    )

    assert response.status_code == 201
    assert response.json()["price"] == 30000
    assert type(response.json()["price"]) is int
    assert _count_active(db_session, other_type.id) == 1


def test_post_rejects_fractional_vnd_without_creating_config(
    client: TestClient, db_session: Session, test_user: User,
):
    """VND không có đơn vị nhỏ hơn đồng: API phải từ chối số thập phân
    thay vì lưu Float rồi để logic tính phí phát sinh số tiền lẻ."""
    vehicle_type = _make_vehicle_type(db_session, "Xe giá lẻ")
    before_count = db_session.query(PriceConfig).count()
    payload = _payload(vehicle_type.id)
    payload["price"] = 30000.5

    response = client.post(
        "/api/v1/price-configs",
        json=payload,
        headers=make_headers(test_user),
    )

    assert response.status_code == 422
    assert "price" in str(response.json()["detail"])
    assert db_session.query(PriceConfig).count() == before_count
    assert (
        db_session.query(PriceConfig)
        .filter(PriceConfig.vehicle_type_id == vehicle_type.id)
        .first()
        is None
    )


def test_post_rejects_negative_vnd_without_creating_config(
    client: TestClient, db_session: Session, test_user: User,
):
    vehicle_type = _make_vehicle_type(db_session, "Xe giá âm")
    before_count = db_session.query(PriceConfig).count()
    payload = _payload(vehicle_type.id)
    payload["price"] = -1

    response = client.post(
        "/api/v1/price-configs",
        json=payload,
        headers=make_headers(test_user),
    )

    assert response.status_code == 422
    assert "price" in str(response.json()["detail"])
    assert db_session.query(PriceConfig).count() == before_count


# ---------------------------------------------------------------------------
# PUT: validate trạng thái SAU MERGE (P1-05)
# ---------------------------------------------------------------------------


def test_put_move_active_config_without_is_active_returns_409(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    """Lỗ hổng gốc: payload không gửi is_active nên guard transition cũ bị
    bỏ qua, bảng giá active được chuyển sang loại xe đã có active khác."""
    other_type = _make_vehicle_type(db_session, "Xe máy")
    other_active = _make_config(db_session, other_type.id, is_active=True)
    before = _snapshot(price_config)

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"vehicle_type_id": other_type.id},
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    assert str(other_active.id) in response.json()["detail"]
    db_session.refresh(price_config)
    assert _snapshot(price_config) == before
    assert _count_active(db_session, other_type.id) == 1


def test_put_move_active_config_with_unchanged_is_active_returns_409(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    """Biến thể UI thật: CrudPage luôn gửi đủ field, is_active=true không đổi
    (true -> true) nên guard transition cũ cũng bị bỏ qua."""
    other_type = _make_vehicle_type(db_session, "Xe máy")
    _make_config(db_session, other_type.id, is_active=True)
    before = _snapshot(price_config)

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={
            "vehicle_type_id": other_type.id,
            "ticket_type": price_config.ticket_type,
            "price": price_config.price,
            "effective_date": price_config.effective_date.isoformat(),
            "is_active": True,
        },
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    db_session.refresh(price_config)
    assert _snapshot(price_config) == before


def test_put_activate_when_other_active_exists_returns_409(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    inactive = _make_config(db_session, vehicle_type.id, is_active=False)

    response = client.put(
        f"/api/v1/price-configs/{inactive.id}",
        json={"is_active": True},
        headers=make_headers(test_user),
    )

    assert response.status_code == 409
    db_session.refresh(inactive)
    assert inactive.is_active is False
    assert _count_active(db_session, vehicle_type.id) == 1


def test_put_activate_after_deactivating_old_one_succeeds(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    """Luồng nghiệp vụ chuẩn: tắt bảng giá cũ trước, rồi kích hoạt bảng mới."""
    headers = make_headers(test_user)
    inactive = _make_config(db_session, vehicle_type.id, is_active=False)

    deactivate = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"is_active": False},
        headers=headers,
    )
    assert deactivate.status_code == 200

    activate = client.put(
        f"/api/v1/price-configs/{inactive.id}",
        json={"is_active": True},
        headers=headers,
    )
    assert activate.status_code == 200
    assert _count_active(db_session, vehicle_type.id) == 1


def test_put_self_update_while_active_does_not_self_conflict(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    """exclude_id: bản ghi active tự sửa giá của chính nó không được coi là
    xung đột với chính nó."""
    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"price": 35000},
        headers=make_headers(test_user),
    )

    assert response.status_code == 200
    assert response.json()["price"] == 35000
    assert response.json()["is_active"] is True


# ---------------------------------------------------------------------------
# P1-04: dữ liệu hỏng sẵn không được biến thành 500
# ---------------------------------------------------------------------------


def test_corrupted_duplicate_actives_return_409_not_500(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    """Mô phỏng DB legacy đã hỏng TỪ TRƯỚC khi có unique index (dữ liệu thật
    của người dùng có thể đang ở trạng thái này): tạm gỡ index để seed bản ghi
    active thứ hai, rồi kiểm tra tầng application vẫn trả 409 rõ ràng và GET
    vẫn hoạt động — tuyệt đối không MultipleResultsFound -> 500."""
    db_session.execute(
        text("DROP INDEX IF EXISTS uq_price_config_one_active_per_vehicle_type")
    )
    db_session.commit()

    _make_config(db_session, vehicle_type.id, is_active=True)
    assert _count_active(db_session, vehicle_type.id) == 2
    headers = make_headers(test_user)

    post_response = client.post(
        "/api/v1/price-configs",
        json=_payload(vehicle_type.id),
        headers=headers,
    )
    assert post_response.status_code == 409

    other = _make_config(
        db_session, _make_vehicle_type(db_session, "Xe máy").id, is_active=True
    )
    put_response = client.put(
        f"/api/v1/price-configs/{other.id}",
        json={"vehicle_type_id": vehicle_type.id},
        headers=headers,
    )
    assert put_response.status_code == 409

    listing = client.get("/api/v1/price-configs", headers=headers)
    assert listing.status_code == 200
    assert _count_active(db_session, vehicle_type.id) == 2  # không đổi thêm


# ---------------------------------------------------------------------------
# DB backstop: unique partial index
# ---------------------------------------------------------------------------


def test_db_index_blocks_second_active_bypassing_api(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig,
):
    """Đường ghi KHÔNG qua router (script seed, sửa DB tay) vẫn phải bị chặn:
    unique partial index là lớp bảo vệ cuối cho bất biến."""
    db_session.add(
        PriceConfig(
            vehicle_type_id=vehicle_type.id,
            ticket_type="DAILY",
            price=200000,
            effective_date=TODAY,
            is_active=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert _count_active(db_session, vehicle_type.id) == 1


def test_db_index_allows_many_inactive_same_vehicle_type(
    db_session: Session, vehicle_type: VehicleType, price_config: PriceConfig,
):
    """Partial index chỉ ràng buộc bản ghi active — lịch sử bảng giá inactive
    của cùng loại xe phải lưu được không giới hạn."""
    for price in (11000, 12000, 13000):
        _make_config(db_session, vehicle_type.id, is_active=False, price=price)

    inactive_count = (
        db_session.query(PriceConfig)
        .filter(
            PriceConfig.vehicle_type_id == vehicle_type.id,
            PriceConfig.is_active == False,  # noqa: E712
        )
        .count()
    )
    assert inactive_count == 3
    assert _count_active(db_session, vehicle_type.id) == 1


@pytest.mark.parametrize("invalid_price", [20000.5, -1])
def test_db_trigger_rejects_invalid_price_bypassing_api(
    db_session: Session,
    vehicle_type: VehicleType,
    invalid_price,
):
    db_session.add(
        PriceConfig(
            vehicle_type_id=vehicle_type.id,
            ticket_type="HOURLY",
            price=invalid_price,
            effective_date=TODAY,
            is_active=False,
        )
    )

    with pytest.raises(IntegrityError, match="price must be nonnegative integer"):
        db_session.commit()

    db_session.rollback()
    assert db_session.query(PriceConfig).count() == 0


def test_db_trigger_rejects_fractional_price_update_bypassing_api(
    db_session: Session,
    vehicle_type: VehicleType,
):
    config = PriceConfig(
        vehicle_type_id=vehicle_type.id,
        ticket_type="HOURLY",
        price=20000,
        effective_date=TODAY,
        is_active=False,
    )
    db_session.add(config)
    db_session.commit()
    config_id = config.id

    config.price = 20000.5
    with pytest.raises(IntegrityError, match="price must be nonnegative integer"):
        db_session.commit()

    db_session.rollback()
    assert db_session.get(PriceConfig, config_id).price == 20000


def test_migration_creates_index_on_legacy_table(tmp_path):
    """DB cũ đã có bảng price_configs nhưng chưa có index: run_sqlite_migrations
    phải tạo được index, và index đó thật sự chặn bản ghi active thứ hai."""
    from sqlalchemy import create_engine

    from database import run_sqlite_migrations

    db_file = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    with legacy_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE price_configs ("
            " id INTEGER PRIMARY KEY, vehicle_type_id INTEGER NOT NULL,"
            " ticket_type VARCHAR(20), price FLOAT, effective_date DATE,"
            " is_active BOOLEAN, created_at DATETIME, updated_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO price_configs (vehicle_type_id, ticket_type, price,"
            " effective_date, is_active) VALUES (1, 'HOURLY', 20000, '2026-01-01', 1)"
        )

    run_sqlite_migrations(legacy_engine)

    with legacy_engine.begin() as conn:
        names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='price_configs'"
            )
        }
        trigger_names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
                " AND tbl_name='price_configs'"
            )
        }
        assert "uq_price_config_one_active_per_vehicle_type" in names
        assert "trg_price_configs_integer_price_insert" in trigger_names
        assert "trg_price_configs_integer_price_update" in trigger_names

        # Legacy FLOAT affinity lưu 20001 dưới dạng REAL 20001.0,
        # nhưng vẫn là số nguyên VND về mặt giá trị và phải được cho phép.
        conn.exec_driver_sql(
            "INSERT INTO price_configs (vehicle_type_id, ticket_type, price,"
            " effective_date, is_active) VALUES "
            "(2, 'HOURLY', 20001, '2026-01-01', 0)"
        )

    # Chạy lại phải idempotent (không lỗi)
    run_sqlite_migrations(legacy_engine)

    with pytest.raises(IntegrityError):
        with legacy_engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO price_configs (vehicle_type_id, ticket_type, price,"
                " effective_date, is_active) VALUES (1, 'DAILY', 90000, '2026-02-01', 1)"
            )

    with pytest.raises(IntegrityError, match="price must be nonnegative integer"):
        with legacy_engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE price_configs SET price = 123.5 "
                "WHERE vehicle_type_id = 2"
            )
    legacy_engine.dispose()


def test_migration_fails_loudly_on_fractional_legacy_price_without_rounding(
    tmp_path,
):
    """Không được âm thầm CAST/làm tròn dữ liệu Float cũ khi chuyển contract
    sang INTEGER. Startup/rollout phải dừng và chỉ rõ bản ghi cần dọn."""
    from sqlalchemy import create_engine

    from database import run_sqlite_migrations

    db_file = tmp_path / "legacy-fractional-price.db"
    legacy_engine = create_engine(f"sqlite:///{db_file.as_posix()}")
    with legacy_engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE price_configs ("
            " id INTEGER PRIMARY KEY, vehicle_type_id INTEGER NOT NULL,"
            " ticket_type VARCHAR(20), price FLOAT, effective_date DATE,"
            " is_active BOOLEAN, created_at DATETIME, updated_at DATETIME)"
        )
        conn.exec_driver_sql(
            "INSERT INTO price_configs (id, vehicle_type_id, ticket_type, price,"
            " effective_date, is_active) VALUES "
            "(77, 1, 'HOURLY', 20000.5, '2026-01-01', 1)"
        )

    with pytest.raises(RuntimeError, match=r"price_configs.*77|77.*price_configs"):
        run_sqlite_migrations(legacy_engine)

    with legacy_engine.connect() as conn:
        stored = conn.exec_driver_sql(
            "SELECT price, typeof(price) FROM price_configs WHERE id = 77"
        ).one()
        index_names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='price_configs'"
            )
        }

    assert stored == (20000.5, "real")
    assert "uq_price_config_one_active_per_vehicle_type" not in index_names
    legacy_engine.dispose()


# ---------------------------------------------------------------------------
# Explicit null và extra field trong partial update
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    ["vehicle_type_id", "ticket_type", "price", "effective_date", "is_active"],
)
def test_update_rejects_explicit_null(
    field_name: str,
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    before = _snapshot(price_config)
    headers = make_headers(test_user)

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={field_name: None},
        headers=headers,
    )

    assert response.status_code == 422
    assert field_name in str(response.json()["detail"])
    db_session.refresh(price_config)
    assert _snapshot(price_config) == before

    listing = client.get("/api/v1/price-configs", headers=headers)
    assert listing.status_code == 200


def test_update_rejects_unknown_field(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    before = _snapshot(price_config)

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"bogus_field": 1},
        headers=make_headers(test_user),
    )

    assert response.status_code == 422
    db_session.refresh(price_config)
    assert _snapshot(price_config) == before


def test_partial_update_price_only_keeps_other_fields(
    client: TestClient, db_session: Session, test_user: User,
    vehicle_type: VehicleType, price_config: PriceConfig,
):
    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"price": 99000},
        headers=make_headers(test_user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["price"] == 99000
    assert type(body["price"]) is int
    assert body["vehicle_type_id"] == vehicle_type.id
    assert body["ticket_type"] == "HOURLY"
    assert body["is_active"] is True


@pytest.mark.parametrize("invalid_price", [99000.5, -1], ids=["fractional", "negative"])
def test_put_rejects_invalid_vnd_without_changing_config(
    invalid_price: float,
    client: TestClient, db_session: Session, test_user: User,
    price_config: PriceConfig,
):
    before = _snapshot(price_config)

    response = client.put(
        f"/api/v1/price-configs/{price_config.id}",
        json={"price": invalid_price},
        headers=make_headers(test_user),
    )

    assert response.status_code == 422
    assert "price" in str(response.json()["detail"])
    db_session.refresh(price_config)
    assert _snapshot(price_config) == before


def test_price_contract_and_new_database_column_use_integer_vnd(
    client: TestClient,
):
    """Khóa contract ở cả HTTP/OpenAPI lẫn DDL cho database tạo mới."""
    schemas = client.app.openapi()["components"]["schemas"]

    assert schemas["PriceConfigCreate"]["properties"]["price"] == {
        "type": "integer",
        "minimum": 0.0,
        "maximum": float(MAX_EXACT_VND),
        "title": "Price",
    }
    update_price = schemas["PriceConfigUpdate"]["properties"]["price"]
    assert update_price["anyOf"][0]["type"] == "integer"
    assert update_price["anyOf"][0]["minimum"] == 0.0
    assert update_price["anyOf"][0]["maximum"] == float(MAX_EXACT_VND)
    assert schemas["PriceConfigResponse"]["properties"]["price"]["type"] == "integer"

    assert isinstance(PriceConfig.__table__.c.price.type, Integer)


def test_api_rejects_price_above_exact_legacy_float_range(
    client: TestClient,
    test_user: User,
    vehicle_type: VehicleType,
):
    response = client.post(
        "/api/v1/price-configs",
        json={
            "vehicle_type_id": vehicle_type.id,
            "ticket_type": "HOURLY",
            "price": MAX_EXACT_VND + 1,
            "effective_date": "2026-08-01",
            "is_active": True,
        },
        headers=make_headers(test_user),
    )
    assert response.status_code == 422


def test_database_rejects_unsupported_ticket_type(
    db_session: Session,
    price_config: PriceConfig,
):
    price_config.ticket_type = "MONTHLY"
    with pytest.raises(
        IntegrityError,
        match="ticket type must be HOURLY or DAILY",
    ):
        db_session.commit()


def test_database_rejects_price_above_exact_vnd_range(
    db_session: Session,
    price_config: PriceConfig,
):
    price_config.price = MAX_EXACT_VND + 1
    with pytest.raises(IntegrityError, match="price exceeds exact VND range"):
        db_session.commit()


@pytest.mark.parametrize(
    ("ticket_type", "price", "message"),
    [
        ("MONTHLY", 25_000, "ticket_type"),
        ("HOURLY", MAX_EXACT_VND + 1, "số nguyên VND"),
    ],
)
def test_migration_rejects_unsafe_legacy_billing_contract(
    tmp_path,
    ticket_type,
    price,
    message,
):
    from sqlalchemy import create_engine
    from database import run_sqlite_migrations

    database_path = tmp_path / f"unsafe-billing-{ticket_type}.db"
    legacy_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE price_configs ("
            "id INTEGER PRIMARY KEY, vehicle_type_id INTEGER NOT NULL, "
            "ticket_type VARCHAR(20), price FLOAT, effective_date DATE, "
            "is_active BOOLEAN)"
        )
        connection.exec_driver_sql(
            "INSERT INTO price_configs(id, vehicle_type_id, ticket_type, price, "
            "effective_date, is_active) VALUES (1, 1, ?, ?, '2026-01-01', 1)",
            (ticket_type, price),
        )

    with pytest.raises(RuntimeError, match=message):
        run_sqlite_migrations(legacy_engine)
