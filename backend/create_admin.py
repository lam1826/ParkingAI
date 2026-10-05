"""
Script tạo các vai trò chuẩn (admin, manager, staff, customer) và tài khoản
admin đầu tiên cho hệ thống.

Cách 1 - chạy tương tác (đứng trong thư mục backend/, đã kích hoạt venv):
    python create_admin.py

Cách 2 - truyền thẳng qua tham số dòng lệnh (hữu ích nếu terminal không gõ
được password ẩn qua getpass):
    python create_admin.py --username admin --password "MatKhau123" --full-name "Quan Tri Vien"

An toàn khi chạy nhiều lần: vai trò chuẩn đã có được giữ nguyên, vai trò còn
thiếu được bổ sung; nếu username đã tồn tại, script sẽ báo và không tạo trùng.
Tên đăng nhập/họ tên được kiểm tra cùng quy tắc với API quản lý tài khoản.

Script không tạo/migration bảng. Hãy chạy ``db_rollout.py`` và xác minh
``GET /ready`` trước; schema thiếu hoặc stale sẽ bị từ chối fail-closed.
"""

import argparse
import sys

import bcrypt
from pydantic import ValidationError

from crud.role import ensure_canonical_roles
from database import SessionLocal, engine
from db_rollout import check_database_readiness
from models.role import Role
from models.user import User
from schemas.user import UserBase


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


def validate_identity(username: str, full_name: str, role_id: int) -> str | None:
    """Same username/full-name rules as POST /api/v1/users; returns an error text."""
    try:
        UserBase.model_validate({"username": username, "full_name": full_name, "role_id": role_id})
    except ValidationError as exc:
        fields = ", ".join(sorted({str(error["loc"][0]) for error in exc.errors()}))
        return f"Thông tin không hợp lệ ({fields}): tên đăng nhập 3-50 ký tự A-Z, a-z, 0-9, _ . -; họ tên 2-100 ký tự."
    return None


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
        # 1. Đảm bảo đủ vai trò chuẩn (admin, manager, staff, customer) để trang
        #    Tài khoản tạo được nhân viên ngay sau khi cài mới.
        created_roles = ensure_canonical_roles(db)
        db.commit()
        if created_roles:
            print(f"[OK] Đã tạo vai trò chuẩn: {', '.join(created_roles)}")
        else:
            print("[SKIP] Các vai trò chuẩn đã tồn tại")
        admin_role = db.query(Role).filter(Role.name == "admin").one()

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

        full_name = (args.full_name or input("Họ tên hiển thị: ")).strip() or username
        problem = validate_identity(username, full_name, admin_role.id)
        if problem:
            print(f"[LỖI] {problem}")
            sys.exit(1)

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
