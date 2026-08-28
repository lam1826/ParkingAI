"""Restore exactly one legacy administrator into the configured database.

This recovery command is intentionally narrower than the full SQLite importer:
it reads only the active ``admin`` account and its role, refuses to overwrite an
existing username, and never prints the password hash.

The source file should be copied to the application machine temporarily and
removed immediately after a successful restore::

    python restore_legacy_admin.py --source /tmp/parkingai-legacy.db \
      --confirm-legacy-admin
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import bcrypt
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from db_rollout import check_database_readiness
from models.role import Role
from models.user import User


@dataclass(frozen=True)
class LegacyAdmin:
    username: str
    password_hash: str
    full_name: str


def _read_legacy_admin(source: Path) -> LegacyAdmin:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    sidecars = [
        Path(f"{source}{suffix}")
        for suffix in ("-wal", "-shm", "-journal")
        if Path(f"{source}{suffix}").exists()
    ]
    if sidecars:
        raise RuntimeError(
            "SQLite nguồn đang hoạt động; tìm thấy sidecar: "
            + ", ".join(item.name for item in sidecars)
        )

    with sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT u.username, u.password_hash, u.full_name, u.is_active,
                   r.name AS role_name
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            WHERE lower(u.username) = lower('admin')
            """
        ).fetchall()

    if len(rows) != 1:
        raise RuntimeError(
            "SQLite nguồn phải có đúng một tài khoản admin; "
            f"tìm thấy {len(rows)}"
        )

    row = rows[0]
    if str(row["role_name"]).lower() != "admin":
        raise RuntimeError("Tài khoản nguồn không thuộc role admin")
    if not bool(row["is_active"]):
        raise RuntimeError("Tài khoản admin nguồn đang bị khóa")

    password_hash = str(row["password_hash"])
    try:
        bcrypt.checkpw(b"parkingai-hash-validation", password_hash.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Hash mật khẩu admin nguồn không phải bcrypt hợp lệ") from exc

    return LegacyAdmin(
        username=str(row["username"]),
        password_hash=password_hash,
        full_name=str(row["full_name"] or row["username"]),
    )


def restore_legacy_admin(source: Path, db: Session) -> User:
    """Insert the active legacy admin without exposing or changing its password."""
    legacy = _read_legacy_admin(source)

    existing = (
        db.query(User)
        .filter(func.lower(User.username) == legacy.username.lower())
        .first()
    )
    if existing is not None:
        raise RuntimeError(
            f"Username '{legacy.username}' đã tồn tại; từ chối ghi đè"
        )

    admin_role = (
        db.query(Role).filter(func.lower(Role.name) == "admin").first()
    )
    if admin_role is None:
        admin_role = Role(
            name="admin",
            description="Quản trị viên hệ thống",
        )
        db.add(admin_role)
        db.flush()

    restored = User(
        username=legacy.username,
        password_hash=legacy.password_hash,
        full_name=legacy.full_name,
        role_id=admin_role.id,
        is_active=True,
    )
    db.add(restored)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(restored)
    return restored


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Khôi phục duy nhất tài khoản admin từ SQLite cũ"
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--confirm-legacy-admin",
        action="store_true",
        help="Xác nhận chỉ chèn admin nếu username chưa tồn tại",
    )
    args = parser.parse_args()
    if not args.confirm_legacy_admin:
        raise SystemExit("Thiếu --confirm-legacy-admin")

    check_database_readiness(engine, deep=True)
    with SessionLocal() as db:
        restored = restore_legacy_admin(args.source, db)
        print(
            "[THÀNH CÔNG] Đã khôi phục tài khoản "
            f"'{restored.username}' (id={restored.id}, role=admin)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
