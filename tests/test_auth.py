import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.user import User
from models.role import Role


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
