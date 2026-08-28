"""Regression tests for the one-time legacy administrator recovery command."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from models.user import User
from restore_legacy_admin import restore_legacy_admin
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
