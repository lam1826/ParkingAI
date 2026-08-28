import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.role import Role
from models.user import User
from models.vehicle_type import VehicleType
from services.auth_service import AuthService


def make_headers(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db_session: Session) -> User:
    role = Role(name="admin", description="Quản trị viên")
    db_session.add(role)
    db_session.flush()
    user = User(
        username="api_admin",
        password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8"),
        full_name="API Admin",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def manager_user(db_session: Session) -> User:
    role = Role(name="manager", description="Quản lý")
    db_session.add(role)
    db_session.flush()
    user = User(
        username="api_manager",
        password_hash=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8"),
        full_name="API Manager",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_user_api_returns_role_and_supports_create(
    client: TestClient,
    db_session: Session,
    admin_user: User,
):
    headers = make_headers(admin_user)
    staff_role = Role(name="staff", description="Nhân viên")
    db_session.add(staff_role)
    db_session.commit()
    db_session.refresh(staff_role)

    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "new_staff_api",
            "password": "password123",
            "full_name": "Nhân viên API",
            "role_id": staff_role.id,
            "is_active": True,
        },
    )
    assert created.status_code == 201
    assert created.json()["role"]["name"] == "staff"

    listed = client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 200
    assert {item["username"] for item in listed.json()} == {"api_admin", "new_staff_api"}
    assert all("role" in item for item in listed.json())


def test_manager_can_view_users_but_cannot_modify(
    client: TestClient,
    manager_user: User,
):
    headers = make_headers(manager_user)

    users = client.get("/api/v1/users", headers=headers)
    roles = client.get("/api/v1/roles", headers=headers)
    assert users.status_code == 200
    assert users.json()[0]["username"] == "api_manager"
    assert roles.status_code == 200

    create = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "forbidden_user",
            "password": "password123",
            "full_name": "Không được tạo",
            "role_id": manager_user.role_id,
            "is_active": True,
        },
    )
    assert create.status_code == 403


def test_admin_cannot_rename_canonical_role_and_keeps_access(
    client: TestClient,
    db_session: Session,
    admin_user: User,
):
    """Canonical role names are part of the authorization contract."""
    headers = make_headers(admin_user)

    response = client.put(
        f"/api/v1/roles/{admin_user.role_id}",
        headers=headers,
        json={"name": "manager", "description": "Tên mới"},
    )

    assert response.status_code == 409
    assert "không thể đổi tên" in response.json()["detail"].lower()
    db_session.refresh(admin_user.role)
    assert admin_user.role.name == "admin"
    assert client.get("/api/v1/roles", headers=headers).status_code == 200


def test_admin_cannot_delete_canonical_role(
    client: TestClient,
    admin_user: User,
):
    response = client.delete(
        f"/api/v1/roles/{admin_user.role_id}",
        headers=make_headers(admin_user),
    )

    assert response.status_code == 409
    assert "vai trò hệ thống" in response.json()["detail"].lower()


def test_legacy_custom_role_does_not_break_role_list_serialization(
    client: TestClient,
    db_session: Session,
    admin_user: User,
):
    """Response đọc dữ liệu cũ không được chạy lại validator của write contract."""
    db_session.add(Role(name="legacy-operator", description="Dữ liệu từ bản cũ"))
    db_session.commit()

    response = client.get(
        "/api/v1/roles",
        headers=make_headers(admin_user),
    )

    assert response.status_code == 200
    assert "legacy-operator" in {item["name"] for item in response.json()}


def test_vehicle_api_accepts_guest_and_returns_related_data(
    client: TestClient,
    test_user: User,
    vehicle_type: VehicleType,
):
    response = client.post(
        "/api/v1/vehicles",
        headers=make_headers(test_user),
        json={
            "license_plate": " 51f-123.45 ",
            "vehicle_type_id": vehicle_type.id,
            "customer_id": "",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["license_plate"] == "51F-123.45"
    assert data["vehicle_type"]["id"] == vehicle_type.id
    assert data["customer"] is None


def test_vehicle_api_reports_missing_relation(
    client: TestClient,
    test_user: User,
):
    response = client.post(
        "/api/v1/vehicles",
        headers=make_headers(test_user),
        json={
            "license_plate": "30A-404.00",
            "vehicle_type_id": 99999,
            "customer_id": None,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Loại xe không tồn tại"
