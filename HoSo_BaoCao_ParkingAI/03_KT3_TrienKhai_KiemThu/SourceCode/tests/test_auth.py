import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.user import User
from models.role import Role
from models.audit_log import AuditLog
from services.auth_service import AuthService
from core.config import settings


def test_login_success(client: TestClient, test_user: User):
    """1. Kiểm thử đăng nhập thành công với thông tin chính xác."""
    response = client.post(
        "/auth/login",
        data={
            "username": test_user.username,
            "password": "password123"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient, test_user: User):
    """2. Kiểm thử đăng nhập thất bại khi sai mật khẩu."""
    response = client.post(
        "/auth/login",
        data={
            "username": test_user.username,
            "password": "wrong_password_xyz"
        }
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Sai tên đăng nhập hoặc mật khẩu"


def test_failed_anonymous_login_is_audited_without_credentials(
    client: TestClient,
    db_session: Session,
    test_user: User,
):
    response = client.post(
        "/api/auth/login",
        headers={"Fly-Client-IP": "203.0.113.8"},
        json={"username": test_user.username, "password": "not-the-password"},
    )

    assert response.status_code == 401
    audit = db_session.query(AuditLog).filter(AuditLog.path == "/api/auth/login").one()
    assert audit.action == "LOGIN"
    assert audit.username == "anonymous"
    assert audit.user_id is None
    assert audit.ip_address == "203.0.113.8"
    assert audit.success is False


def test_login_rate_limit_blocks_brute_force_by_fly_client_ip(
    client: TestClient,
    test_user: User,
    monkeypatch,
):
    monkeypatch.setattr(settings, "AUTH_LOGIN_MAX_FAILURES", 2)
    headers = {"Fly-Client-IP": "203.0.113.9"}

    for _ in range(2):
        failed = client.post(
            "/api/auth/login",
            headers=headers,
            json={"username": test_user.username, "password": "wrong-password"},
        )
        assert failed.status_code == 401

    blocked = client.post(
        "/api/auth/login",
        headers=headers,
        json={"username": test_user.username, "password": "password123"},
    )

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == str(settings.AUTH_LOGIN_WINDOW_SECONDS)


def test_registration_rate_limit_counts_successful_account_creation(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "AUTH_REGISTER_MAX_ATTEMPTS", 1)
    headers = {"Fly-Client-IP": "203.0.113.10"}
    payload = {
        "username": "rate_limited_customer",
        "password": "password123",
        "full_name": "Khách giới hạn",
        "role": "customer",
    }

    created = client.post("/api/auth/register", headers=headers, json=payload)
    blocked = client.post(
        "/api/auth/register",
        headers=headers,
        json={**payload, "username": "another_customer"},
    )

    assert created.status_code == 201
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == str(settings.AUTH_REGISTER_WINDOW_SECONDS)


def test_login_wrong_username(client: TestClient, test_user: User):
    """3. Kiểm thử đăng nhập thất bại khi sai tên đăng nhập."""
    response = client.post(
        "/auth/login",
        data={
            "username": "non_existent_username_123",
            "password": "password123"
        }
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Sai tên đăng nhập hoặc mật khẩu"


def test_login_inactive_user(client: TestClient, db_session: Session, role: Role):
    """4. Kiểm thử đăng nhập thất bại khi tài khoản bị khóa."""
    hashed_password = bcrypt.hashpw(
        "password123".encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    locked_user = User(
        username="locked_staff",
        role_id=role.id,
        password_hash=hashed_password,
        full_name="Nhân viên bị khóa",
        is_active=False
    )

    db_session.add(locked_user)
    db_session.commit()

    response = client.post(
        "/auth/login",
        data={
            "username": "locked_staff",
            "password": "password123"
        }
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Tài khoản đã bị khóa"


def test_login_empty_username(client: TestClient):
    """5. Kiểm thử đăng nhập với trường username để trống (trả về 422 từ FastAPI Form validation)."""
    response = client.post(
        "/auth/login",
        data={
            "username": "",
            "password": "password123"
        }
    )

    assert response.status_code == 422


def test_login_empty_password(client: TestClient, test_user: User):
    """6. Kiểm thử đăng nhập với trường password để trống.

    OAuth2PasswordRequestForm coi cả username và password là Form field bắt
    buộc không rỗng, nên chuỗi rỗng bị FastAPI chặn ở tầng validation (422)
    trước khi chạm tới logic xác thực - giống hệt hành vi của
    test_login_empty_username ở trên.
    """
    response = client.post(
        "/auth/login",
        data={
            "username": test_user.username,
            "password": ""
        }
    )

    assert response.status_code == 422


def test_customer_registration_success(client: TestClient, db_session: Session):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "new_customer",
            "password": "password123",
            "full_name": "Khách hàng mới",
            "role": "customer",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "customer"
    created = db_session.query(User).filter(User.username == "new_customer").one()
    assert created.role.name == "customer"
    assert bcrypt.checkpw(b"password123", created.password_hash.encode("utf-8"))


def test_privileged_registration_requires_valid_code(client: TestClient, db_session: Session):
    denied = client.post(
        "/api/auth/register",
        json={
            "username": "new_admin",
            "password": "password123",
            "full_name": "Quản trị mới",
            "role": "admin",
            "registration_code": "wrong-code",
        },
    )
    assert denied.status_code == 403
    assert db_session.query(User).filter(User.username == "new_admin").first() is None

    accepted = client.post(
        "/api/auth/register",
        json={
            "username": "new_admin",
            "password": "password123",
            "full_name": "Quản trị mới",
            "role": "admin",
            "registration_code": "admin-test-code",
        },
    )
    assert accepted.status_code == 201
    assert accepted.json()["role"] == "admin"


def test_manager_registration_with_valid_code(client: TestClient, db_session: Session):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "new_manager",
            "password": "password123",
            "full_name": "Quản lý mới",
            "role": "manager",
            "registration_code": "manager-test-code",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "manager"
    created = db_session.query(User).filter(User.username == "new_manager").one()
    assert created.role.name == "manager"


def test_duplicate_registration_returns_conflict(client: TestClient, test_user: User):
    response = client.post(
        "/api/auth/register",
        json={
            "username": test_user.username,
            "password": "password123",
            "full_name": "Trùng tên",
            "role": "customer",
        },
    )
    assert response.status_code == 409


def test_customer_cannot_access_staff_dashboard(client: TestClient):
    registered = client.post(
        "/api/auth/register",
        json={
            "username": "limited_customer",
            "password": "password123",
            "full_name": "Khách giới hạn",
            "role": "customer",
        },
    )
    assert registered.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={"username": "limited_customer", "password": "password123"},
    )
    assert login.status_code == 200

    response = client.get(
        "/dashboard",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 403


def auth_headers_for(user: User) -> dict[str, str]:
    token = AuthService().create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )
    return {"Authorization": f"Bearer {token}"}


def test_user_can_update_own_profile(client: TestClient, test_user: User):
    response = client.put(
        "/api/auth/me",
        headers=auth_headers_for(test_user),
        json={"username": "qa_staff_updated", "full_name": "Nhân viên QA cập nhật"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "qa_staff_updated"
    assert data["full_name"] == "Nhân viên QA cập nhật"
    assert data["role"] == "staff"


def test_profile_update_rejects_duplicate_username(
    client: TestClient,
    db_session: Session,
    test_user: User,
    role: Role,
):
    other = User(
        username="existing_user",
        password_hash=AuthService.get_password_hash("password123"),
        full_name="Người dùng khác",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(other)
    db_session.commit()

    response = client.put(
        "/api/auth/me",
        headers=auth_headers_for(test_user),
        json={"username": "existing_user", "full_name": "Nhân viên QA"},
    )
    assert response.status_code == 409


def test_user_can_change_password(client: TestClient, test_user: User):
    headers = auth_headers_for(test_user)
    wrong = client.put(
        "/api/auth/me/password",
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "new-password-123"},
    )
    assert wrong.status_code == 400

    changed = client.put(
        "/api/auth/me/password",
        headers=headers,
        json={"current_password": "password123", "new_password": "new-password-123"},
    )
    assert changed.status_code == 200

    old_login = client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": "password123"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": "new-password-123"},
    )
    assert new_login.status_code == 200
