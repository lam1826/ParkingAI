"""
Script tạo role "admin" và tài khoản admin đầu tiên cho hệ thống.

Cách 1 - chạy tương tác (đứng trong thư mục backend/, đã kích hoạt venv):
    python create_admin.py

Cách 2 - truyền thẳng qua tham số dòng lệnh (hữu ích nếu terminal không gõ
được password ẩn qua getpass):
    python create_admin.py --username admin --password "MatKhau123" --full-name "Quan Tri Vien"

An toàn khi chạy nhiều lần: nếu role "admin" hoặc username đã tồn tại,
script sẽ báo và không tạo trùng.

Script không tạo/migration bảng. Hãy chạy ``db_rollout.py`` và xác minh
``GET /ready`` trước; schema thiếu hoặc stale sẽ bị từ chối fail-closed.
"""

import argparse
import sys

import bcrypt

from database import SessionLocal, engine
from db_rollout import check_database_readiness
from models.role import Role
from models.user import User


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def prompt_password() -> str:
    """Thử dùng getpass (ẩn ký tự); nếu terminal không hỗ trợ thì
    tự động chuyển sang input() bình thường (gõ thấy chữ)."""
    import getpass
    try:
        pw = getpass.getpass("Password: ")
        # Một số terminal (VS Code, PowerShell ISE...) không chặn được stdin,
        # getpass trả về chuỗi rỗng ngay lập tức -> coi là không hỗ trợ.
        if pw != "":
            return pw
        print("(Terminal này có vẻ không hỗ trợ ẩn mật khẩu, chuyển sang nhập bình thường)")
    except Exception:
        print("(Terminal này không hỗ trợ ẩn mật khẩu, chuyển sang nhập bình thường)")
    return input("Password (sẽ hiện ra khi gõ): ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo tài khoản admin đầu tiên")
    parser.add_argument("--username", help="Username cho admin")
    parser.add_argument("--password", help="Password (nếu không truyền sẽ hỏi qua terminal)")
    parser.add_argument("--full-name", dest="full_name", help="Họ tên hiển thị")
    args = parser.parse_args()

    try:
        check_database_readiness(engine, deep=True)
    except Exception as exc:
        print(
            "[LỖI] Database chưa sẵn sàng. Hãy chạy db_rollout.py trên "
            f"đúng file trước khi tạo admin: {exc}"
        )
        sys.exit(1)

    db = SessionLocal()
    try:
        # 1. Đảm bảo có role "admin"
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if admin_role is None:
            admin_role = Role(name="admin", description="Quản trị viên hệ thống")
            db.add(admin_role)
            db.commit()
            db.refresh(admin_role)
            print(f"[OK] Đã tạo role 'admin' (id={admin_role.id})")
        else:
            print(f"[SKIP] Role 'admin' đã tồn tại (id={admin_role.id})")

        # 2. Lấy thông tin tài khoản admin (từ tham số dòng lệnh hoặc hỏi qua terminal)
        username = args.username or input("Username cho admin: ").strip()
        username = username.strip()
        if not username:
            print("Username không được để trống.")
            sys.exit(1)

        existing = db.query(User).filter(User.username == username).first()
        if existing is not None:
            print(f"[LỖI] Username '{username}' đã tồn tại (id={existing.id}). Không tạo trùng.")
            sys.exit(1)

        full_name = args.full_name or input("Họ tên hiển thị: ").strip() or username

        if args.password:
            password = args.password
        else:
            password = prompt_password()
            password_confirm = prompt_password()
            if password != password_confirm:
                print("[LỖI] Hai lần nhập password không khớp.")
                sys.exit(1)

        if len(password) < 6:
            print("[LỖI] Password nên có ít nhất 6 ký tự.")
            sys.exit(1)

        admin_user = User(
            username=username,
            role_id=admin_role.id,
            password_hash=get_password_hash(password),
            full_name=full_name,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print(f"\n[THÀNH CÔNG] Đã tạo tài khoản admin '{username}' (id={admin_user.id}).")
        print("Dùng tài khoản này để đăng nhập qua POST /auth/login.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
