"""Regression tests for the one-time legacy administrator recovery command."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from models.role import Role
from models.user import User
from restore_legacy_admin import (
    export_legacy_privileged_transfer,
    restore_legacy_admin,
    restore_legacy_privileged_users,
)
from services.auth_service import AuthService


def _write_legacy_user(
    path: Path,
    *,
    role: str = "admin",
    username: str = "admin",
    password: str = "legacy-password",
) -> None:
    with sqlite3.connect(path) as connection:
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
        connection.execute(
            "INSERT INTO roles(id, name) VALUES (1, ?)",
            (role,),
        )
        connection.execute(
            """
            INSERT INTO users(
                id, role_id, username, password_hash, full_name, is_active
            ) VALUES (1, 1, ?, ?, 'Quản trị viên', 1)
            """,
            (username, AuthService.get_password_hash(password)),
        )


def _append_legacy_manager(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO roles(id, name) VALUES (2, 'manager')"
        )
        connection.execute(
            """
            INSERT INTO users(
                id, role_id, username, password_hash, full_name, is_active
            ) VALUES (2, 2, 'manager', ?, 'Quản lý bãi xe', 1)
            """,
            (AuthService.get_password_hash("legacy-manager-password"),),
        )


def test_restore_legacy_privileged_users_is_atomic_and_preserves_passwords(
    tmp_path: Path,
    db_session: Session,
) -> None:
    source = tmp_path / "legacy.db"
    _write_legacy_user(source)
    _append_legacy_manager(source)

    restored = restore_legacy_privileged_users(source, db_session)

    assert [(user.username, user.role.name) for user in restored] == [
        ("admin", "admin"),
        ("manager", "manager"),
    ]
    assert AuthService.verify_password(
        "legacy-password",
        restored[0].password_hash,
    )
    assert AuthService.verify_password(
        "legacy-manager-password",
        restored[1].password_hash,
    )
    assert db_session.query(User).count() == 2


def test_restore_privileged_users_writes_nothing_when_one_username_exists(
    tmp_path: Path,
    db_session: Session,
) -> None:
    source = tmp_path / "legacy.db"
    _write_legacy_user(source)
    _append_legacy_manager(source)
    manager_role = Role(name="manager")
    db_session.add(manager_role)
    db_session.flush()
    db_session.add(
        User(
            username="manager",
            password_hash=AuthService.get_password_hash("existing-password"),
            full_name="Existing Manager",
            role_id=manager_role.id,
            is_active=True,
        )
    )
    db_session.commit()

    with pytest.raises(RuntimeError, match="manager.*đã tồn tại"):
        restore_legacy_privileged_users(source, db_session)

    assert [user.username for user in db_session.query(User).all()] == ["manager"]
    assert db_session.query(Role).filter(Role.name == "admin").first() is None


def test_export_privileged_transfer_contains_only_two_required_accounts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    transfer = tmp_path / "transfer.db"
    _write_legacy_user(source)
    _append_legacy_manager(source)

    export_legacy_privileged_transfer(source, transfer)

    with sqlite3.connect(transfer) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        accounts = connection.execute(
            """
            SELECT u.username, r.name
            FROM users AS u
            JOIN roles AS r ON r.id = u.role_id
            ORDER BY u.id
            """
        ).fetchall()

    assert tables == {"roles", "users"}
    assert accounts == [("admin", "admin"), ("manager", "manager")]


def test_restore_legacy_admin_preserves_password_and_admin_role(
    tmp_path: Path,
    db_session: Session,
) -> None:
    source = tmp_path / "legacy.db"
    _write_legacy_user(source)

    restored = restore_legacy_admin(source, db_session)

    assert restored.username == "admin"
    assert restored.role.name == "admin"
    assert restored.is_active is True
    assert AuthService.verify_password("legacy-password", restored.password_hash)
    assert db_session.query(User).count() == 1


def test_restore_legacy_admin_refuses_non_admin_source(
    tmp_path: Path,
    db_session: Session,
) -> None:
    source = tmp_path / "legacy.db"
    _write_legacy_user(source, role="staff")

    with pytest.raises(RuntimeError, match="role admin"):
        restore_legacy_admin(source, db_session)

    assert db_session.query(User).count() == 0


def test_restore_legacy_admin_never_overwrites_existing_username(
    tmp_path: Path,
    db_session: Session,
) -> None:
    source = tmp_path / "legacy.db"
    _write_legacy_user(source)
    restore_legacy_admin(source, db_session)

    with pytest.raises(RuntimeError, match="đã tồn tại"):
        restore_legacy_admin(source, db_session)

    assert db_session.query(User).count() == 1
