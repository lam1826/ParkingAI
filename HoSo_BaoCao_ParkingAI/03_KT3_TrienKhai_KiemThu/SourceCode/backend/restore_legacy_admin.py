"""Restore the legacy administrator and manager into the configured database.

This recovery command is intentionally narrower than the full SQLite importer:
it reads only the active ``admin`` and ``manager`` accounts, refuses to
overwrite any existing username, commits both accounts atomically, and never
prints a password hash.

The source file should be copied to the application machine temporarily and
removed immediately after a successful restore::

    python restore_legacy_admin.py --source /tmp/parkingai-legacy.db \
      --confirm-admin-and-manager
"""

from __future__ import annotations

import argparse
import os
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
class LegacyPrivilegedUser:
    username: str
    password_hash: str
    full_name: str
    role_name: str


ROLE_DESCRIPTIONS = {
    "admin": "Quản trị viên hệ thống",
    "manager": "Quản lý bãi đỗ xe",
}


def _read_legacy_users(
    source: Path,
    required_roles: tuple[str, ...],
) -> list[LegacyPrivilegedUser]:
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
        placeholders = ", ".join("?" for _ in required_roles)
        rows = connection.execute(
            f"""
            SELECT u.username, u.password_hash, u.full_name, u.is_active,
                   r.name AS role_name
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            WHERE lower(u.username) IN ({placeholders})
            """,
            required_roles,
        ).fetchall()

    rows_by_role = {str(row["role_name"]).lower(): row for row in rows}
    if set(rows_by_role) != set(required_roles) or len(rows) != len(required_roles):
        raise RuntimeError(
            "SQLite nguồn thiếu hoặc trùng tài khoản role "
            + ", ".join(required_roles)
        )

    result = []
    for role_name in required_roles:
        row = rows_by_role[role_name]
        username = str(row["username"])
        if username.lower() != role_name:
            raise RuntimeError(
                f"Tài khoản role {role_name} phải có username '{role_name}'"
            )
        if not bool(row["is_active"]):
            raise RuntimeError(f"Tài khoản {username} nguồn đang bị khóa")

        password_hash = str(row["password_hash"])
        try:
            bcrypt.checkpw(
                b"parkingai-hash-validation",
                password_hash.encode("utf-8"),
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Hash mật khẩu {username} nguồn không phải bcrypt hợp lệ"
            ) from exc

        result.append(
            LegacyPrivilegedUser(
                username=username,
                password_hash=password_hash,
                full_name=str(row["full_name"] or username),
                role_name=role_name,
            )
        )
    return result


def _read_legacy_admin(source: Path) -> LegacyPrivilegedUser:
    return _read_legacy_users(source, ("admin",))[0]


def export_legacy_privileged_transfer(source: Path, destination: Path) -> None:
    """Create a minimal 0600 SQLite payload containing only admin and manager."""
    legacy_users = _read_legacy_users(source, ("admin", "manager"))
    destination = destination.resolve()
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)

    descriptor = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(descriptor)
    try:
        with sqlite3.connect(destination) as connection:
            connection.executescript(
                """
                CREATE TABLE roles (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    role_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    is_active INTEGER NOT NULL
                );
                """
            )
            for index, legacy in enumerate(legacy_users, start=1):
                connection.execute(
                    "INSERT INTO roles(id, name) VALUES (?, ?)",
                    (index, legacy.role_name),
                )
                connection.execute(
                    """
                    INSERT INTO users(
                        id, role_id, username, password_hash,
                        full_name, is_active
                    ) VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (
                        index,
                        index,
                        legacy.username,
                        legacy.password_hash,
                        legacy.full_name,
                    ),
                )
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def _restore_legacy_users(
    source: Path,
    db: Session,
    required_roles: tuple[str, ...],
) -> list[User]:
    legacy_users = _read_legacy_users(source, required_roles)

    for legacy in legacy_users:
        existing = (
            db.query(User)
            .filter(func.lower(User.username) == legacy.username.lower())
            .first()
        )
        if existing is not None:
            raise RuntimeError(
                f"Username '{legacy.username}' đã tồn tại; từ chối ghi đè"
            )

    roles_by_name = {
        role.name.lower(): role
        for role in db.query(Role).filter(
            func.lower(Role.name).in_(required_roles)
        )
    }
    restored_users = []
    for legacy in legacy_users:
        role = roles_by_name.get(legacy.role_name)
        if role is None:
            role = Role(
                name=legacy.role_name,
                description=ROLE_DESCRIPTIONS[legacy.role_name],
            )
            db.add(role)
            db.flush()
            roles_by_name[legacy.role_name] = role

        restored = User(
            username=legacy.username,
            password_hash=legacy.password_hash,
            full_name=legacy.full_name,
            role_id=role.id,
            is_active=True,
        )
        db.add(restored)
        restored_users.append(restored)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    for restored in restored_users:
        db.refresh(restored)
    return restored_users


def restore_legacy_admin(source: Path, db: Session) -> User:
    """Insert the active legacy admin without exposing or changing its password."""
    return _restore_legacy_users(source, db, ("admin",))[0]


def restore_legacy_privileged_users(source: Path, db: Session) -> list[User]:
    """Atomically restore the active legacy admin and manager accounts."""
    return _restore_legacy_users(source, db, ("admin", "manager"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Khôi phục tài khoản admin và manager từ SQLite cũ"
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--export-minimal-to",
        type=Path,
        help="Tạo payload chỉ chứa admin/manager; không kết nối DB đích",
    )
    parser.add_argument(
        "--confirm-admin-and-manager",
        action="store_true",
        help="Xác nhận chèn nguyên tử admin và manager nếu chưa tồn tại",
    )
    args = parser.parse_args()
    if args.export_minimal_to is not None:
        export_legacy_privileged_transfer(args.source, args.export_minimal_to)
        print(
            "[THÀNH CÔNG] Đã tạo payload tối thiểu gồm "
            "2 role và 2 tài khoản đặc quyền."
        )
        return 0
    if not args.confirm_admin_and_manager:
        raise SystemExit("Thiếu --confirm-admin-and-manager")

    check_database_readiness(engine, deep=True)
    with SessionLocal() as db:
        restored_users = restore_legacy_privileged_users(args.source, db)
        for restored in restored_users:
            print(
                "[THÀNH CÔNG] Đã khôi phục tài khoản "
                f"'{restored.username}' (id={restored.id}, "
                f"role={restored.role.name})."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
