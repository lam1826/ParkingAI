from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from crud import customer as customer_crud
from models.customer import Customer
from models.monthly_pass import MonthlyPass
from models.vehicle import Vehicle
from schemas.customer import CustomerCreate, CustomerUpdate
from services.auth_service import AuthService


def _headers(user) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


def test_customer_create_normalizes_writable_fields(
    client: TestClient,
    test_user,
):
    response = client.post(
        "/api/v1/customers",
        headers=_headers(test_user),
        json={
            "full_name": "  Nguyễn Văn Bình  ",
            "phone_number": "  0912345678  ",
            "email": "  BINH@Example.COM  ",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "full_name": "Nguyễn Văn Bình",
        "phone_number": "0912345678",
        "email": "binh@example.com",
    }


def test_customer_create_accepts_blank_optional_email_from_crud_form(
    client: TestClient,
    test_user,
):
    response = client.post(
        "/api/v1/customers",
        headers=_headers(test_user),
        json={
            "full_name": "Khách không email",
            "phone_number": "0912000000",
            "email": "   ",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] is None


@pytest.mark.parametrize("method", ["post", "put"])
def test_customer_write_rejects_extra_fields(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
    method: str,
):
    before_count = db_session.query(Customer).count()
    if method == "post":
        response = client.post(
            "/api/v1/customers",
            headers=_headers(test_user),
            json={
                "full_name": "Khách lạ",
                "phone_number": "0988000000",
                "bogus_field": "silent-drop",
            },
        )
    else:
        response = client.put(
            f"/api/v1/customers/{customer.id}",
            headers=_headers(test_user),
            json={"bogus_field": "silent-drop"},
        )

    assert response.status_code == 422
    assert db_session.query(Customer).count() == before_count


@pytest.mark.parametrize("field", ["full_name", "phone_number"])
def test_customer_update_rejects_explicit_null_for_required_fields(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
    field: str,
):
    before = (customer.full_name, customer.phone_number, customer.email)

    response = client.put(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
        json={field: None},
    )

    assert response.status_code == 422
    db_session.refresh(customer)
    assert (customer.full_name, customer.phone_number, customer.email) == before


def test_customer_update_allows_null_email_to_clear_it(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
):
    customer.email = "old@example.com"
    db_session.commit()

    response = client.put(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
        json={"email": None},
    )

    assert response.status_code == 200
    assert response.json()["email"] is None
    db_session.refresh(customer)
    assert customer.email is None


def test_customer_create_rejects_normalized_duplicate_phone_with_409(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
):
    response = client.post(
        "/api/v1/customers",
        headers=_headers(test_user),
        json={
            "full_name": "Người trùng số",
            "phone_number": f"  {customer.phone_number}  ",
        },
    )

    assert response.status_code == 409
    assert "số điện thoại" in response.json()["detail"].lower()
    assert db_session.query(Customer).filter_by(phone_number=customer.phone_number).count() == 1


def test_customer_update_rejects_phone_owned_by_another_customer_with_409(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
):
    other = Customer(full_name="Khách thứ hai", phone_number="0922222222")
    db_session.add(other)
    db_session.commit()
    original_phone = customer.phone_number

    response = client.put(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
        json={"phone_number": "  0922222222  "},
    )

    assert response.status_code == 409
    assert "số điện thoại" in response.json()["detail"].lower()
    db_session.refresh(customer)
    assert customer.phone_number == original_phone


def test_db_index_rejects_phone_duplicate_after_unicode_trim_normalization(
    db_session: Session,
):
    db_session.add(
        Customer(full_name="Khách legacy", phone_number="  0912888999  ")
    )
    db_session.commit()

    db_session.add(
        Customer(full_name="Khách trùng chuẩn hóa", phone_number="0912888999")
    )
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
    assert db_session.query(Customer).count() == 1


def test_customer_api_detects_normalized_legacy_phone_with_specific_409(
    client: TestClient,
    db_session: Session,
    test_user,
):
    # Mô phỏng row legacy/ghi ngoài API còn khoảng trắng. Lookup của
    # router phải dùng cùng quy tắc chuẩn hóa với unique index.
    db_session.add(
        Customer(full_name="Khách legacy", phone_number="  0912777888  ")
    )
    db_session.commit()

    response = client.post(
        "/api/v1/customers",
        headers=_headers(test_user),
        json={
            "full_name": "Khách race",
            "phone_number": "0912777888",
        },
    )

    assert response.status_code == 409
    assert "số điện thoại" in response.json()["detail"].lower()
    assert db_session.query(Customer).count() == 1


def test_customer_phone_migration_fails_loudly_on_normalized_duplicates(tmp_path):
    from sqlalchemy import create_engine

    from database import run_sqlite_migrations

    engine = create_engine(f"sqlite:///{(tmp_path / 'customers-dup.db').as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE customers ("
            "id INTEGER PRIMARY KEY, full_name VARCHAR(100), "
            "phone_number VARCHAR(20), email VARCHAR(100))"
        )
        conn.exec_driver_sql(
            "INSERT INTO customers (id, full_name, phone_number) VALUES "
            "(1, 'A', '  0912666777  '), (2, 'B', '0912666777')"
        )

    with pytest.raises(RuntimeError, match=r"customers\.phone_number|customers.*trùng"):
        run_sqlite_migrations(engine)

    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT id, phone_number FROM customers ORDER BY id"
        ).all()
        index_names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='customers'"
            )
        }

    assert rows == [(1, "  0912666777  "), (2, "0912666777")]
    assert "uq_customers_phone_normalized" not in index_names
    engine.dispose()


def test_customer_phone_migration_installs_normalized_unique_index(tmp_path):
    from sqlalchemy import create_engine

    from database import run_sqlite_migrations

    engine = create_engine(f"sqlite:///{(tmp_path / 'customers-valid.db').as_posix()}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE customers ("
            "id INTEGER PRIMARY KEY, full_name VARCHAR(100), "
            "phone_number VARCHAR(20), email VARCHAR(100))"
        )
        conn.exec_driver_sql(
            "INSERT INTO customers (id, full_name, phone_number) "
            "VALUES (1, 'A', '  0912555666  ')"
        )

    run_sqlite_migrations(engine)
    run_sqlite_migrations(engine)

    with engine.connect() as conn:
        index_names = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND tbl_name='customers'"
            )
        }
    assert "uq_customers_phone_normalized" in index_names

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO customers (id, full_name, phone_number) "
                "VALUES (2, 'B', '0912555666')"
            )
    engine.dispose()


def test_customer_delete_with_vehicle_returns_409_and_preserves_relationship(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
    vehicle: Vehicle,
):
    vehicle.customer_id = customer.id
    db_session.commit()

    response = client.delete(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "phương tiện" in response.json()["detail"].lower()
    assert db_session.get(Customer, customer.id) is not None
    db_session.refresh(vehicle)
    assert vehicle.customer_id == customer.id


def test_customer_delete_with_monthly_pass_returns_409_and_preserves_history(
    client: TestClient,
    db_session: Session,
    test_user,
    customer: Customer,
    vehicle: Vehicle,
):
    monthly_pass = MonthlyPass(
        customer_id=customer.id,
        vehicle_id=vehicle.id,
        pass_code="CUSTOMER-HISTORY",
        price=500_000,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1) + timedelta(days=30),
        is_active=False,
    )
    db_session.add(monthly_pass)
    db_session.commit()

    response = client.delete(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
    )

    assert response.status_code == 409
    assert "vé tháng" in response.json()["detail"].lower()
    assert db_session.get(Customer, customer.id) is not None
    db_session.refresh(monthly_pass)
    assert monthly_pass.customer_id == customer.id


def test_customer_valid_update_and_delete_without_history_still_work(
    client: TestClient,
    db_session: Session,
    test_user,
):
    customer = Customer(
        full_name="Khách có thể xóa",
        phone_number="0933333333",
        email="before@example.com",
    )
    db_session.add(customer)
    db_session.commit()

    updated = client.put(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
        json={
            "full_name": "  Tên sau cập nhật  ",
            "phone_number": "  0944444444  ",
            "email": "  AFTER@Example.COM  ",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Tên sau cập nhật"
    assert updated.json()["phone_number"] == "0944444444"
    assert updated.json()["email"] == "after@example.com"

    deleted = client.delete(
        f"/api/v1/customers/{customer.id}",
        headers=_headers(test_user),
    )
    assert deleted.status_code == 204
    assert db_session.get(Customer, customer.id) is None


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_customer_crud_rolls_back_when_commit_fails(operation: str):
    db = MagicMock()
    db.commit.side_effect = SQLAlchemyError("commit failed")
    existing = Customer(id=77, full_name="Khách", phone_number="0909000000")

    with pytest.raises(SQLAlchemyError, match="commit failed"):
        if operation == "create":
            customer_crud.create_customer(
                db,
                CustomerCreate(full_name="Mới", phone_number="0909000001"),
            )
        elif operation == "update":
            customer_crud.update_customer(
                db,
                existing,
                CustomerUpdate(full_name="Đổi tên"),
            )
        else:
            customer_crud.delete_customer(db, existing)

    db.rollback.assert_called_once_with()
