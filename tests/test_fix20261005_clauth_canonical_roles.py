"""CL-AUTH #41: a fresh install has every canonical role, so staff can be created.

The documented bootstrap (db_rollout.py, then create_admin.py) runs against a
throw-away SQLite file under pytest's tmp_path, never a real database.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from core.roles import CANONICAL_ROLE_NAMES
from crud import role as crud_role
from models.role import Role

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"


def _run(args, cwd, env):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)


def _bootstrap_env(database: Path):
    env = dict(os.environ)
    env.update({"DATABASE_URL": f"sqlite:///{database.as_posix()}", "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    return env


def test_documented_fresh_bootstrap_creates_all_canonical_roles(tmp_path):
    database = tmp_path / "fresh_install.db"
    env = _bootstrap_env(database)
    rollout = _run([sys.executable, "-B", "backend/db_rollout.py", "--database", str(database)], REPO, env)
    assert rollout.returncode == 0, rollout.stdout[-800:] + rollout.stderr[-800:]

    rejected = _run([sys.executable, "-B", "create_admin.py", "--username", "admin@parking.vn",
                     "--password", "Secret123!", "--full-name", "Quan Tri"], BACKEND, env)
    assert rejected.returncode != 0 and "Thông tin không hợp lệ" in rejected.stdout, rejected.stdout

    created = _run([sys.executable, "-B", "create_admin.py", "--username", "rootadmin",
                    "--password", "Secret123!", "--full-name", "Quan Tri"], BACKEND, env)
    assert created.returncode == 0, created.stdout[-800:] + created.stderr[-800:]
    rerun = _run([sys.executable, "-B", "create_admin.py", "--username", "secondadmin",
                  "--password", "Secret123!", "--full-name", "Quan Tri 2"], BACKEND, env)
    assert rerun.returncode == 0, rerun.stdout[-800:] + rerun.stderr[-800:]

    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.connect() as connection:
            names = [row[0] for row in connection.execute(text("SELECT name FROM roles ORDER BY name"))]
            users = [row[0] for row in connection.execute(text("SELECT username FROM users ORDER BY username"))]
    finally:
        engine.dispose()
    assert names == sorted(CANONICAL_ROLE_NAMES)
    assert users == ["rootadmin", "secondadmin"]


def _run_create_admin(monkeypatch, db_session, *argv):
    """In-process create_admin.main() on the pytest DB, independent of rollout DDL."""
    import create_admin
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(create_admin, "check_database_readiness", lambda *args, **kwargs: None)
    monkeypatch.setattr(create_admin, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    monkeypatch.setattr(sys, "argv", ["create_admin.py", *argv])
    try:
        create_admin.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_create_admin_seeds_roles_and_validates_identity_in_process(monkeypatch, db_session, capsys):
    assert _run_create_admin(monkeypatch, db_session, "--username", "admin@parking.vn",
                             "--password", "Secret123!", "--full-name", "Quan Tri") == 1
    assert "Thông tin không hợp lệ" in capsys.readouterr().out
    assert _run_create_admin(monkeypatch, db_session, "--username", "rootadmin",
                             "--password", "Secret123!", "--full-name", "a") == 1
    assert _run_create_admin(monkeypatch, db_session, "--username", "rootadmin",
                             "--password", "Secret123!", "--full-name", "Quan Tri") == 0
    db_session.expire_all()
    assert {row.name for row in db_session.query(Role).all()} == set(CANONICAL_ROLE_NAMES)
    from models.user import User
    assert [(user.username, user.role.name) for user in db_session.query(User).all()] == [("rootadmin", "admin")]


def test_ensure_canonical_roles_is_idempotent_and_keeps_existing_rows(db_session):
    existing = Role(name="staff", description="Mô tả riêng của bãi")
    db_session.add(existing)
    db_session.commit()
    first = crud_role.ensure_canonical_roles(db_session)
    db_session.commit()
    second = crud_role.ensure_canonical_roles(db_session)
    db_session.commit()
    rows = {row.name: row for row in db_session.query(Role).all()}
    assert set(rows) == set(CANONICAL_ROLE_NAMES)
    assert rows["staff"].id == existing.id and rows["staff"].description == "Mô tả riêng của bãi"
    assert sorted(first) == sorted(CANONICAL_ROLE_NAMES - {"staff"})
    assert second == []


def test_privileged_registration_on_an_empty_install_also_provides_staff(client, db_session):
    response = client.post("/api/auth/register", json={
        "username": "first_manager", "password": "Secret123!", "full_name": "Quản lý đầu tiên",
        "role": "manager", "registration_code": os.environ["MANAGER_REGISTRATION_CODE"]})
    assert response.status_code == 201, response.text
    assert {row.name for row in db_session.query(Role).all()} == set(CANONICAL_ROLE_NAMES)
