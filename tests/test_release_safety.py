"""Regression tests for explicit, copy-first database rollout and AI fail-closed mode.

These tests never open the two real workspace databases. Every path comes from
pytest's temporary directory and Gemini's client is always mocked.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from core.config import settings
from services.ai_service import AIService


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_parking_slot_state(
    connection: sqlite3.Connection,
    *,
    is_occupied: bool,
    has_active_session: bool,
) -> None:
    """Create the smallest valid graph needed to express slot occupancy."""
    connection.create_function(
        "unicode_casefold",
        1,
        lambda value: value.casefold() if value is not None else None,
        deterministic=True,
    )
    connection.executescript(
        f"""
        INSERT INTO roles(id, name, description)
        VALUES (1, 'manager-release-test', NULL);
        INSERT INTO users(
            id, role_id, username, password_hash, full_name, is_active
        ) VALUES (
            1, 1, 'release-test-user', 'not-a-real-hash',
            'Release Test User', 1
        );
        INSERT INTO vehicle_types(id, name, description, is_active)
        VALUES (1, 'release-test-type', NULL, 1);
        INSERT INTO zones(id, name, capacity, is_active)
        VALUES (1, 'release-test-zone', 1, 1);
        INSERT INTO parking_slots(
            id, zone_id, vehicle_type_id, slot_name, is_occupied, is_active
        ) VALUES (
            1, 1, 1, 'RELEASE-SLOT-1', {int(is_occupied)}, 1
        );
        INSERT INTO vehicles(id, license_plate, vehicle_type_id, customer_id)
        VALUES (1, 'REL-001', 1, NULL);
        INSERT INTO price_configs(
            id, vehicle_type_id, ticket_type, price, effective_date, is_active
        ) VALUES (1, 1, 'HOURLY', 25000, '2026-01-01', 1);
        """
    )
    if has_active_session:
        connection.execute(
            """
            INSERT INTO parking_sessions(
                id, vehicle_id, parking_slot_id, monthly_pass_id,
                check_in_time, check_out_time, image_in_url, image_out_url,
                parking_fee, status, staff_in_id, staff_out_id
            ) VALUES (
                'release-session-1', 1, 1, NULL,
                '2026-08-27 08:00:00', NULL, NULL, NULL,
                NULL, 'active', 1, NULL
            )
            """
        )
    connection.commit()


def _windows_acl_dump(path: Path) -> str:
    completed = subprocess.run(
        ["icacls.exe", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.replace(str(path), "<PATH>").strip()


def test_importing_main_does_not_create_or_migrate_database(tmp_path: Path) -> None:
    """Importing ASGI code must be read-only; migration is an explicit command."""
    database_path = tmp_path / "must-not-be-created.db"
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "SECRET_KEY": "subprocess-test-secret-key",
            "AI_ENABLED": "false",
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (str(backend_dir), inherited_pythonpath)
                if part
            ),
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not database_path.exists(), (
        "Chỉ import main không được tạo/kết nối/migrate database. "
        "Hãy chạy lệnh migration tường minh trước khi khởi động app."
    )


def test_importing_database_module_does_not_create_default_directory(
    tmp_path: Path,
) -> None:
    """Ngay cả import module thấp nhất cũng phải là filesystem read-only."""
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    isolated_dir = tmp_path / "isolated-backend"
    isolated_dir.mkdir()
    shutil.copy2(backend_dir / "database.py", isolated_dir / "database.py")
    isolated_core = isolated_dir / "core"
    isolated_core.mkdir()
    shutil.copy2(backend_dir / "core" / "money.py", isolated_core / "money.py")

    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    env.update(
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "PYTHONPATH": os.pathsep.join(
                part for part in (str(isolated_dir), inherited_pythonpath) if part
            ),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import database"],
        cwd=isolated_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not (isolated_dir / "database").exists()


def test_importing_create_admin_does_not_create_database(tmp_path: Path) -> None:
    """Admin bootstrap may insert an account, but may not bootstrap schema."""
    database_path = tmp_path / "admin-import-must-not-create.db"
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    env = os.environ.copy()
    inherited_pythonpath = env.get("PYTHONPATH")
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (str(backend_dir), inherited_pythonpath)
                if part
            ),
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", "import create_admin"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not database_path.exists()


def test_readiness_is_503_and_does_not_create_a_missing_database(
    tmp_path: Path,
) -> None:
    """Liveness may stay up, but readiness must fail read-only on a bad path."""
    from main import app

    database_path = tmp_path / "missing-readiness.db"
    missing_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with patch("main.engine", missing_engine):
            response = TestClient(app).get("/ready")
    finally:
        missing_engine.dispose()

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert not database_path.exists()


def test_readiness_is_200_only_after_explicit_verified_rollout(
    tmp_path: Path,
) -> None:
    from db_rollout import initialize_database
    from main import app

    database_path = tmp_path / "ready.db"
    initialize_database(database_path)
    ready_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with patch("main.engine", ready_engine):
            response = TestClient(app).get("/ready")
    finally:
        ready_engine.dispose()

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_http_readiness_uses_lightweight_schema_probe() -> None:
    """Frequent unauthenticated probes must not run full integrity scans."""
    import main

    with patch("main.check_database_readiness") as readiness_check:
        response = TestClient(main.app).get("/ready")

    assert response.status_code == 200
    readiness_check.assert_called_once_with(main.engine, deep=False)


@pytest.mark.parametrize(
    ("is_occupied", "has_active_session"),
    [
        (False, True),
        (True, False),
    ],
)
def test_readiness_rejects_slot_occupancy_that_disagrees_with_active_session(
    tmp_path: Path,
    is_occupied: bool,
    has_active_session: bool,
) -> None:
    """Both directions of the denormalized occupancy invariant are required."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "slot-occupancy-drift.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=is_occupied,
            has_active_session=has_active_session,
        )
    connection.close()
    database_before = database_path.read_bytes()
    mtime_before = database_path.stat().st_mtime_ns

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"is_occupied.*active"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()
    assert database_path.read_bytes() == database_before
    assert database_path.stat().st_mtime_ns == mtime_before


def test_rollout_rejects_slot_occupancy_drift_without_rewriting_target(
    tmp_path: Path,
) -> None:
    """Rollout validates legacy business data on its candidate and fails closed."""
    from db_rollout import initialize_database

    database_path = tmp_path / "rollout-slot-occupancy-drift.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=False,
            has_active_session=True,
        )
    connection.close()

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match=r"is_occupied.*active"):
        initialize_database(database_path)

    assert database_path.read_bytes() == database_before


def test_readiness_rejects_active_session_without_fallback_rate(
    tmp_path: Path,
) -> None:
    from database import (
        SESSION_RATE_INSERT_VALIDATION_TRIGGER_SQL,
        TRG_SESSION_RATE_INSERT_VALIDATION,
    )
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "readiness-missing-rate.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=True,
            has_active_session=False,
        )
        connection.execute("DELETE FROM price_configs")
        connection.execute(f"DROP TRIGGER {TRG_SESSION_RATE_INSERT_VALIDATION}")
        connection.execute(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, parking_slot_id, monthly_pass_id, "
            "check_in_time, status, staff_in_id) VALUES "
            "('unpriced-active', 1, 1, NULL, '2026-08-27 08:00:00', "
            "'active', 1)"
        )
        connection.execute(SESSION_RATE_INSERT_VALIDATION_TRIGGER_SQL)
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="thiếu bảng giá hiệu lực"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()


def test_readiness_rejects_invalid_session_monthly_pass_snapshot(
    tmp_path: Path,
) -> None:
    from database import (
        SESSION_MONTHLY_PASS_INSERT_VALIDATION_TRIGGER_SQL,
        TRG_SESSION_MONTHLY_PASS_INSERT_VALIDATION,
    )
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "readiness-invalid-entitlement.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=True,
            has_active_session=False,
        )
        connection.executescript(
            """
            INSERT INTO customers(id, full_name, phone_number, email)
            VALUES (1, 'Release Customer', '0900000999', NULL);
            INSERT INTO monthly_passes(
                id, customer_id, vehicle_id, pass_code, price,
                start_date, end_date, is_active
            ) VALUES (
                1, 1, 1, 'RELEASE-PASS', 500000,
                '2026-08-28', '2026-09-28', 1
            );
            """
        )
        connection.execute(
            f"DROP TRIGGER {TRG_SESSION_MONTHLY_PASS_INSERT_VALIDATION}"
        )
        connection.execute(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, parking_slot_id, monthly_pass_id, "
            "check_in_time, status, staff_in_id) VALUES "
            "('bad-pass-link', 1, 1, 1, '2026-08-27 08:00:00', "
            "'active', 1)"
        )
        connection.execute(SESSION_MONTHLY_PASS_INSERT_VALIDATION_TRIGGER_SQL)
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="quyền lợi vé tháng"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()


def test_readiness_rejects_active_slot_vehicle_type_mismatch(
    tmp_path: Path,
) -> None:
    from database import (
        SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL,
        TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION,
    )
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "readiness-slot-type-mismatch.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=False,
            has_active_session=False,
        )
        connection.execute(
            "INSERT INTO vehicle_types(id, name, description, is_active) "
            "VALUES (2, 'release-other-type', NULL, 1)"
        )
        connection.execute(
            "UPDATE parking_slots SET vehicle_type_id=2 WHERE id=1"
        )
        connection.execute(
            "UPDATE parking_slots SET is_occupied=1 WHERE id=1"
        )
        connection.execute(
            f"DROP TRIGGER {TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION}"
        )
        connection.execute(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, parking_slot_id, monthly_pass_id, "
            "check_in_time, status, staff_in_id) VALUES "
            "('slot-type-mismatch', 1, 1, NULL, "
            "'2026-08-27 08:00:00', 'active', 1)"
        )
        connection.execute(SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL)
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="loại xe"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()


def test_readiness_and_rollout_reject_active_session_on_inactive_zone(
    tmp_path: Path,
) -> None:
    from database import (
        SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL,
        TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION,
    )
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "readiness-inactive-zone-session.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=False,
            has_active_session=False,
        )
        connection.execute("UPDATE zones SET is_active=0 WHERE id=1")
        connection.execute("UPDATE parking_slots SET is_occupied=1 WHERE id=1")
        connection.execute(
            f"DROP TRIGGER {TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION}"
        )
        connection.execute(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, parking_slot_id, monthly_pass_id, "
            "check_in_time, status, staff_in_id) VALUES "
            "('inactive-zone-session', 1, 1, NULL, "
            "'2026-08-27 08:00:00', 'active', 1)"
        )
        connection.execute(SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL)
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="admission"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match="vị trí/zone không hoạt động"):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before


def test_rollout_rejects_active_session_when_price_table_was_missing(
    tmp_path: Path,
) -> None:
    """create_all must not turn a skipped legacy preflight into ready=true."""
    from database import (
        TRG_PRICE_ACTIVE_SESSION_DELETE_GUARD,
        TRG_PRICE_ACTIVE_SESSION_UPDATE_GUARD,
        TRG_SESSION_RATE_INSERT_VALIDATION,
    )
    from db_rollout import initialize_database

    database_path = tmp_path / "legacy-missing-price-table.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=True,
            has_active_session=False,
        )
        connection.execute(f"DROP TRIGGER {TRG_SESSION_RATE_INSERT_VALIDATION}")
        connection.execute(f"DROP TRIGGER {TRG_PRICE_ACTIVE_SESSION_UPDATE_GUARD}")
        connection.execute(f"DROP TRIGGER {TRG_PRICE_ACTIVE_SESSION_DELETE_GUARD}")
        connection.execute("DROP TABLE price_configs")
        connection.execute(
            "INSERT INTO parking_sessions "
            "(id, vehicle_id, parking_slot_id, monthly_pass_id, "
            "check_in_time, status, staff_in_id) VALUES "
            "('legacy-unpriced', 1, 1, NULL, '2026-08-27 08:00:00', "
            "'active', 1)"
        )
        connection.commit()

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match="thiếu bảng giá hiệu lực"):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before


@pytest.mark.parametrize(
    ("replacement_id", "vehicle_type_id", "is_active"),
    [
        (2, 1, 1),
        (1, 2, 0),
        (1, 2, 1),
    ],
    ids=["unique-active-type", "primary-key-deactivate", "primary-key-retarget"],
)
def test_external_sqlite_replace_cannot_bypass_active_rate_lock(
    tmp_path: Path,
    replacement_id: int,
    vehicle_type_id: int,
    is_active: int,
) -> None:
    """The DB backstop must work even when a tool leaves recursive triggers OFF."""
    from db_rollout import initialize_database

    database_path = tmp_path / "external-replace-rate.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone() == (0,)
        _seed_parking_slot_state(
            connection,
            is_occupied=True,
            has_active_session=True,
        )
        connection.execute(
            "INSERT OR IGNORE INTO vehicle_types"
            "(id, name, description, is_active) "
            "VALUES (2, 'replacement-other-type', NULL, 1)"
        )

        with pytest.raises(
            sqlite3.IntegrityError,
            match="active parking session uses price config",
        ):
            connection.execute(
                "INSERT OR REPLACE INTO price_configs "
                "(id, vehicle_type_id, ticket_type, price, effective_date, "
                "is_active) VALUES (?, ?, 'HOURLY', 999999, "
                "'2026-01-01', ?)",
                (replacement_id, vehicle_type_id, is_active),
            )

        assert connection.execute(
            "SELECT id, price FROM price_configs ORDER BY id"
        ).fetchall() == [(1, 25000)]


@pytest.mark.parametrize(
    ("table_name", "column_name"),
    [
        ("users", "is_active"),
        ("vehicle_types", "is_active"),
        ("zones", "is_active"),
        ("parking_slots", "is_active"),
        ("parking_slots", "is_occupied"),
        ("monthly_passes", "is_active"),
        ("price_configs", "is_active"),
        ("audit_logs", "success"),
    ],
)
def test_db_rejects_noncanonical_boolean_values(
    tmp_path: Path,
    table_name: str,
    column_name: str,
) -> None:
    from db_rollout import initialize_database

    database_path = tmp_path / f"boolean-{table_name}-{column_name}.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=False,
            has_active_session=False,
        )
        if table_name == "monthly_passes":
            connection.executescript(
                """
                INSERT INTO customers(id, full_name, phone_number, email)
                VALUES (1, 'Boolean Customer', '0900000888', NULL);
                INSERT INTO monthly_passes(
                    id, customer_id, vehicle_id, pass_code, price,
                    start_date, end_date, is_active
                ) VALUES (
                    1, 1, 1, 'BOOLEAN-PASS', 500000,
                    '2026-08-27', '2026-09-27', 1
                );
                """
            )
        elif table_name == "audit_logs":
            connection.execute(
                "INSERT INTO audit_logs "
                "(id, user_id, username, action, resource, resource_id, "
                "method, path, status_code, success, ip_address) VALUES "
                "(1, 1, 'audit-user', 'CREATE', 'test', NULL, 'POST', "
                "'/test', 200, 1, NULL)"
            )

        with pytest.raises(
            sqlite3.IntegrityError,
            match="boolean value must be 0 or 1",
        ):
            connection.execute(
                f"UPDATE {table_name} SET {column_name}=2 WHERE id=1"
            )


def test_readiness_and_rollout_reject_noncanonical_legacy_boolean(
    tmp_path: Path,
) -> None:
    from database import BOOLEAN_DOMAIN_TRIGGER_SQL
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "legacy-boolean.db"
    initialize_database(database_path)
    update_trigger = "trg_zones_boolean_domain_update"
    with sqlite3.connect(database_path) as connection:
        _seed_parking_slot_state(
            connection,
            is_occupied=False,
            has_active_session=False,
        )
        connection.execute(f"DROP TRIGGER {update_trigger}")
        connection.execute("UPDATE zones SET is_active=2 WHERE id=1")
        connection.execute(BOOLEAN_DOMAIN_TRIGGER_SQL[update_trigger])
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match="boolean 0/1"):
            check_database_readiness(target_engine, deep=False)
    finally:
        target_engine.dispose()

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match="boolean 0/1"):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before


def test_ai_disabled_fails_before_provider_client_is_created(db_session) -> None:
    """A configured key alone must never enable live provider calls in UAT."""
    with (
        patch.object(settings, "AI_ENABLED", False, create=True),
        patch("services.ai_service.genai.Client") as client_factory,
        pytest.raises(HTTPException) as exc_info,
    ):
        AIService(db_session, api_key="configured-but-must-not-be-used")

    assert exc_info.value.status_code == 503
    assert "AI_ENABLED" in exc_info.value.detail
    client_factory.assert_not_called()


def test_ai_enabled_setting_defaults_to_fail_closed() -> None:
    from core.config import Settings

    assert Settings.model_fields["AI_ENABLED"].default is False


def test_migrate_copy_keeps_source_byte_and_mtime_unchanged(tmp_path: Path) -> None:
    """The UAT path upgrades a new copy, never the supplied source database."""
    from db_rollout import initialize_database, migrate_copy

    source = tmp_path / "legacy-source.db"
    output = tmp_path / "uat-copy.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO legacy_marker(value) VALUES ('kept')")
        connection.commit()

    source_hash = _sha256(source)
    source_mtime = source.stat().st_mtime_ns

    migrate_copy(source, output)

    assert _sha256(source) == source_hash
    assert source.stat().st_mtime_ns == source_mtime
    assert output.exists()
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT value FROM legacy_marker").fetchone() == ("kept",)
    connection.close()

    output_engine = create_engine(f"sqlite:///{output.as_posix()}")
    try:
        table_names = set(inspect(output_engine).get_table_names())
        with output_engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
            trigger_names = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                )
            }
    finally:
        output_engine.dispose()
    assert {"parking_sessions", "zones", "parking_slots"} <= table_names
    assert {
        "trg_parking_slots_capacity_insert",
        "trg_parking_slots_capacity_move",
        "trg_zones_capacity_update",
    } <= trigger_names

    # Chạy lại lệnh tường minh phải idempotent và không làm mất dữ liệu copy.
    initialize_database(output)
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT value FROM legacy_marker").fetchone() == ("kept",)


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership semantics only")
def test_initialize_existing_database_preserves_posix_mode_owner_and_group(
    tmp_path: Path,
) -> None:
    from db_rollout import initialize_database

    database_path = tmp_path / "posix-security-metadata.db"
    initialize_database(database_path)
    os.chmod(database_path, 0o640)
    before = database_path.stat()

    initialize_database(database_path)

    after = database_path.stat()
    assert stat.S_IMODE(after.st_mode) == 0o640
    assert after.st_uid == before.st_uid
    assert after.st_gid == before.st_gid


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL semantics only")
def test_initialize_existing_database_preserves_windows_dacl(tmp_path: Path) -> None:
    """Publishing a candidate must retain the destination's protected DACL."""
    from db_rollout import initialize_database

    database_path = tmp_path / "windows-security-metadata.db"
    initialize_database(database_path)
    completed = subprocess.run(
        ["icacls.exe", str(database_path), "/inheritance:d"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    dacl_before = _windows_acl_dump(database_path)

    initialize_database(database_path)

    assert _windows_acl_dump(database_path) == dacl_before


def test_migrate_copy_refuses_same_path_or_existing_output(tmp_path: Path) -> None:
    from db_rollout import migrate_copy

    source = tmp_path / "source.db"
    source.touch()
    existing_output = tmp_path / "already-exists.db"
    existing_output.write_bytes(b"do-not-overwrite")

    with pytest.raises(ValueError, match="khác"):
        migrate_copy(source, source)
    with pytest.raises(FileExistsError):
        migrate_copy(source, existing_output)
    assert existing_output.read_bytes() == b"do-not-overwrite"


def test_migrate_copy_refuses_live_wal_source_and_publishes_no_output(
    tmp_path: Path,
) -> None:
    """Main-file hash cannot prove logical immutability while WAL is live."""
    from db_rollout import migrate_copy

    source = tmp_path / "live-wal.db"
    output = tmp_path / "must-not-be-published.db"
    with sqlite3.connect(source) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO marker(value) VALUES ('only-in-wal')")
        writer.commit()
        wal_path = Path(f"{source}-wal")
        assert wal_path.exists() and wal_path.stat().st_size > 0
        source_family_before = {
            path.name: path.read_bytes()
            for path in (source, wal_path, Path(f"{source}-shm"))
            if path.exists()
        }

        with pytest.raises(RuntimeError, match="WAL|sidecar|journal"):
            migrate_copy(source, output)

        assert {
            path.name: path.read_bytes()
            for path in (source, wal_path, Path(f"{source}-shm"))
            if path.exists()
        } == source_family_before
        assert not output.exists()


def test_migrate_copy_rejects_sidecar_created_after_initial_cold_check(
    tmp_path: Path,
) -> None:
    """A WAL that appears between preflight and fingerprint must fail closed."""
    import db_rollout

    source = tmp_path / "late-wal.db"
    output = tmp_path / "must-not-publish-late-wal.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")

    original_assert_cold = db_rollout._assert_cold_source

    def create_late_sidecar(path: Path) -> None:
        original_assert_cold(path)
        Path(f"{path}-wal").write_bytes(b"late-wal-must-not-be-ignored")

    with (
        patch("db_rollout._assert_cold_source", side_effect=create_late_sidecar),
        pytest.raises(RuntimeError, match="WAL|sidecar|journal"),
    ):
        db_rollout.migrate_copy(source, output)

    assert not output.exists()


def test_migrate_copy_rejects_persistent_wal_mode_without_sidecars(
    tmp_path: Path,
) -> None:
    """A closed DB can retain WAL mode even after sidecars disappear."""
    from db_rollout import migrate_copy

    source = tmp_path / "persistent-wal.db"
    output = tmp_path / "must-not-publish-persistent-wal.db"
    connection = sqlite3.connect(source)
    try:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        connection.close()

    # Windows may retain empty WAL/SHM files after the final connection closes.
    # Removing those empty temp sidecars models a clean handoff whose database
    # header nevertheless still persists journal_mode=WAL.
    Path(f"{source}-wal").unlink(missing_ok=True)
    Path(f"{source}-shm").unlink(missing_ok=True)
    assert not Path(f"{source}-wal").exists()
    assert not Path(f"{source}-shm").exists()
    source_hash = _sha256(source)
    source_mtime = source.stat().st_mtime_ns

    with pytest.raises(RuntimeError, match=r"journal_mode=WAL.*DELETE"):
        migrate_copy(source, output)

    assert _sha256(source) == source_hash
    assert source.stat().st_mtime_ns == source_mtime
    assert not Path(f"{source}-wal").exists()
    assert not Path(f"{source}-shm").exists()
    assert not output.exists()


def test_migrate_copy_publishes_nothing_when_candidate_schema_is_invalid(
    tmp_path: Path,
) -> None:
    """A failed candidate must never occupy the user-requested output path."""
    from db_rollout import migrate_copy

    source = tmp_path / "stale-source.db"
    output = tmp_path / "candidate.db"
    with sqlite3.connect(source) as connection:
        connection.executescript(
            """
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                capacity INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TABLE parking_slots (
                id INTEGER PRIMARY KEY,
                zone_id INTEGER NOT NULL,
                vehicle_type_id INTEGER NOT NULL,
                slot_name VARCHAR(50) NOT NULL,
                is_occupied BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TRIGGER trg_parking_slots_capacity_insert
            BEFORE INSERT ON parking_slots
            BEGIN SELECT 1; END;
            """
        )

    with pytest.raises(RuntimeError, match="trg_parking_slots_capacity_insert"):
        migrate_copy(source, output)

    assert not output.exists()
    assert not list(tmp_path.glob("*.partial*"))


def test_migrate_copy_never_clobbers_output_created_during_finalize(
    tmp_path: Path,
) -> None:
    """Atomic publication must fail if another process wins the output name."""
    from db_rollout import migrate_copy

    source = tmp_path / "race-source.db"
    output = tmp_path / "race-output.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
    connection.close()

    def competing_publish(_staging, destination):
        Path(destination).write_bytes(b"created-by-another-process")
        raise FileExistsError(destination)

    with (
        patch("db_rollout.os.link", side_effect=competing_publish),
        pytest.raises(FileExistsError),
    ):
        migrate_copy(source, output)

    assert output.read_bytes() == b"created-by-another-process"
    assert not list(tmp_path.glob("*.partial*"))


def test_rollout_cli_survives_legacy_cp1252_console(tmp_path: Path) -> None:
    """Windows console hẹp không được làm lệnh thành công trả exit 1.

    Đường dẫn workspace và thông báo tiếng Việt đều có thể chứa ký tự ngoài
    CP1252. CLI phải escape ký tự không biểu diễn được thay vì crash ở print
    sau khi migration đã hoàn tất.
    """
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    source = tmp_path / "cli-source.db"
    output = tmp_path / "cli-output.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252:strict"
    completed = subprocess.run(
        [
            sys.executable,
            str(backend_dir / "db_rollout.py"),
            "--source",
            str(source),
            "--copy-to",
            str(output),
        ],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=False,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("ascii", "backslashreplace")
    assert output.exists()


def test_initialize_rejects_schema_object_with_right_name_but_wrong_definition(
    tmp_path: Path,
) -> None:
    """IF NOT EXISTS must not silently bless a stale/malicious trigger body."""
    from db_rollout import initialize_database

    database_path = tmp_path / "wrong-trigger.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                capacity INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TABLE parking_slots (
                id INTEGER PRIMARY KEY,
                zone_id INTEGER NOT NULL,
                vehicle_type_id INTEGER NOT NULL,
                slot_name VARCHAR(50) NOT NULL,
                is_occupied BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TRIGGER trg_parking_slots_capacity_insert
            BEFORE INSERT ON parking_slots
            BEGIN SELECT 1; END;
            """
        )

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match="trg_parking_slots_capacity_insert"):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before, (
        "Schema stale phải bị chặn ở preflight trước mọi ALTER/CREATE. "
        "Một rollout báo lỗi không được để DB đích ở trạng thái nâng cấp dở."
    )


def test_initialize_keeps_existing_database_byte_identical_on_late_fk_failure(
    tmp_path: Path,
) -> None:
    """A post-migration validation failure must not partially upgrade target."""
    from db_rollout import initialize_database

    database_path = tmp_path / "late-failure.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO vehicles(license_plate, vehicle_type_id, customer_id) "
            "VALUES ('ORPHAN-01', 999999, NULL)"
        )
        connection.execute(
            "DROP INDEX uq_price_config_one_active_per_vehicle_type"
        )
        connection.commit()

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match="foreign_key_check"):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before


def test_initialize_rejects_same_name_index_with_wrong_unique_columns_or_predicate(
    tmp_path: Path,
) -> None:
    """Tên index đúng không đủ: unique/key/predicate đều là contract bắt buộc."""
    from db_rollout import initialize_database

    database_path = tmp_path / "wrong-index.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE price_configs (
                id INTEGER PRIMARY KEY,
                vehicle_type_id INTEGER NOT NULL,
                ticket_type VARCHAR(20) NOT NULL,
                price INTEGER NOT NULL,
                effective_date DATE NOT NULL,
                is_active BOOLEAN NOT NULL
            );
            CREATE INDEX uq_price_config_one_active_per_vehicle_type
            ON price_configs(id);
            """
        )

    database_before = database_path.read_bytes()
    with pytest.raises(
        RuntimeError,
        match="uq_price_config_one_active_per_vehicle_type",
    ):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before


def test_initialize_rejects_noop_trigger_even_when_all_keywords_are_present(
    tmp_path: Path,
) -> None:
    """Substring matching must not bless a trigger disabled by ``WHEN 0``."""
    from db_rollout import initialize_database

    database_path = tmp_path / "noop-trigger.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                capacity INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TABLE parking_slots (
                id INTEGER PRIMARY KEY,
                zone_id INTEGER NOT NULL,
                vehicle_type_id INTEGER NOT NULL,
                slot_name VARCHAR(50) NOT NULL,
                is_occupied BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE TRIGGER trg_parking_slots_capacity_insert
            BEFORE INSERT ON parking_slots
            WHEN 0
            BEGIN
                SELECT COUNT(*) FROM parking_slots
                WHERE zone_id = NEW.zone_id;
                SELECT RAISE(ABORT, 'zone capacity exceeded');
            END;
            """
        )

    database_before = database_path.read_bytes()
    with pytest.raises(RuntimeError, match="trg_parking_slots_capacity_insert"):
        initialize_database(database_path)
    assert database_path.read_bytes() == database_before


def _required_schema_objects() -> list[tuple[str, str]]:
    """Read the rollout manifests at collection time so this test cannot go
    stale when a required trigger/index is added later."""
    from db_rollout import _REQUIRED_INDEX_SQL, _REQUIRED_TRIGGER_SQL

    return [
        *[("index", name) for name in sorted(_REQUIRED_INDEX_SQL)],
        *[("trigger", name) for name in sorted(_REQUIRED_TRIGGER_SQL)],
    ]


@pytest.mark.parametrize(
    ("object_type", "object_name"),
    _required_schema_objects(),
)
def test_readiness_rejects_wrong_definition_for_every_required_schema_object(
    tmp_path: Path,
    object_type: str,
    object_name: str,
) -> None:
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / f"wrong-{object_name}.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        object_row = connection.execute(
            "SELECT tbl_name FROM sqlite_master WHERE type = ? AND name = ?",
            (object_type, object_name),
        ).fetchone()
        assert object_row is not None, f"Manifest object was not installed: {object_name}"
        table_name = object_row[0]
        quoted_name = object_name.replace('"', '""')
        quoted_table = table_name.replace('"', '""')
        connection.execute(f'DROP {object_type.upper()} "{quoted_name}"')
        if object_type == "index":
            connection.execute(
                f'CREATE INDEX "{quoted_name}" ON "{quoted_table}"(id)'
            )
        else:
            connection.execute(
                f'CREATE TRIGGER "{quoted_name}" BEFORE INSERT ON roles '
                "BEGIN SELECT 1; END"
            )
        connection.commit()

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=object_name):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_readiness_rejects_missing_model_column_and_rollout_preserves_target(
    tmp_path: Path,
) -> None:
    """Indexes/triggers alone cannot make a table with missing columns ready."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "missing-customer-email.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute("ALTER TABLE customers DROP COLUMN email")
        connection.commit()

    before = database_path.read_bytes()
    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"customers\.email"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()

    with pytest.raises(RuntimeError, match=r"customers\.email"):
        initialize_database(database_path)
    assert database_path.read_bytes() == before


def test_readiness_rejects_missing_model_foreign_key(tmp_path: Path) -> None:
    """An empty DB can pass foreign_key_check while its FK DDL is missing."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "missing-ai-report-fk.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE ai_reports_replacement (
                id INTEGER NOT NULL PRIMARY KEY,
                report_type VARCHAR(50) NOT NULL,
                prompt_used TEXT NOT NULL,
                content TEXT NOT NULL,
                generated_by_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
            DROP TABLE ai_reports;
            ALTER TABLE ai_reports_replacement RENAME TO ai_reports;
            """
        )

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"ai_reports.*foreign key"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_readiness_rejects_foreign_key_action_drift(tmp_path: Path) -> None:
    """A cascading FK is not equivalent to the model's NO ACTION history guard."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "cascading-ai-report-fk.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE ai_reports_replacement (
                id INTEGER NOT NULL PRIMARY KEY,
                report_type VARCHAR(50) NOT NULL,
                prompt_used TEXT NOT NULL,
                content TEXT NOT NULL,
                generated_by_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(generated_by_id) REFERENCES users (id)
                    ON DELETE CASCADE
            );
            DROP TABLE ai_reports;
            ALTER TABLE ai_reports_replacement RENAME TO ai_reports;
            """
        )

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"ai_reports.*foreign key"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_readiness_rejects_model_nullability_drift(tmp_path: Path) -> None:
    """A required field made nullable is schema drift even with no bad rows."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "nullable-ai-report-content.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE ai_reports_replacement (
                id INTEGER NOT NULL PRIMARY KEY,
                report_type VARCHAR(50) NOT NULL,
                prompt_used TEXT NOT NULL,
                content TEXT,
                generated_by_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(generated_by_id) REFERENCES users (id)
            );
            DROP TABLE ai_reports;
            ALTER TABLE ai_reports_replacement RENAME TO ai_reports;
            """
        )

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"ai_reports\.content.*nullable"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_readiness_rejects_nullable_text_primary_key(tmp_path: Path) -> None:
    """Only SQLite's implicit INTEGER PK may skip the reflected nullable quirk."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "nullable-session-text-pk.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        create_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'parking_sessions'"
        ).fetchone()[0]
        replacement_sql = create_sql.replace(
            "CREATE TABLE parking_sessions",
            "CREATE TABLE parking_sessions_replacement",
            1,
        ).replace("id VARCHAR(36) NOT NULL", "id VARCHAR(36)", 1)
        assert replacement_sql != create_sql
        connection.executescript(
            f"""
            PRAGMA foreign_keys=OFF;
            DROP TRIGGER trg_zones_operational_update_guard;
            DROP TRIGGER trg_parking_slots_operational_update_guard;
            DROP TRIGGER trg_parking_slots_zone_immutable_with_history;
            DROP TRIGGER trg_vehicles_vehicle_type_immutable_with_history;
                DROP TRIGGER trg_vehicles_license_plate_immutable_with_history;
                DROP TRIGGER trg_monthly_passes_history_immutable;
                    DROP TRIGGER trg_price_configs_active_session_update_guard_v2;
                    DROP TRIGGER trg_price_configs_active_session_delete_guard_v2;
                    DROP TRIGGER trg_price_configs_active_session_replace_guard;
                    {replacement_sql};
            DROP TABLE parking_sessions;
            ALTER TABLE parking_sessions_replacement RENAME TO parking_sessions;
            """
        )

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"parking_sessions\.id.*nullable"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_readiness_rejects_wrong_server_default_value(tmp_path: Path) -> None:
    """Having any default is insufficient; its value is part of the contract."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "wrong-created-at-default.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        create_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'ai_reports'"
        ).fetchone()[0]
        replacement_sql = create_sql.replace(
            "CREATE TABLE ai_reports",
            "CREATE TABLE ai_reports_replacement",
            1,
        ).replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT 0", 1)
        assert replacement_sql != create_sql
        connection.executescript(
            f"""
            PRAGMA foreign_keys=OFF;
            {replacement_sql};
            DROP TABLE ai_reports;
            ALTER TABLE ai_reports_replacement RENAME TO ai_reports;
            """
        )

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"ai_reports\.created_at.*default"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_rollout_installs_named_role_uniqueness_backstop(tmp_path: Path) -> None:
    """Legacy roles tables need the same uniqueness invariant as the ORM model."""
    from db_rollout import initialize_database

    database_path = tmp_path / "role-unique.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        indexes = {
            row[1]: row[2]
            for row in connection.execute("PRAGMA index_list(roles)").fetchall()
        }

    assert indexes.get("uq_roles_name") == 1


def test_readiness_rejects_partial_index_in_place_of_full_unique_constraint(
    tmp_path: Path,
) -> None:
    """A partial username index still permits duplicates outside its predicate."""
    from db_rollout import check_database_readiness, initialize_database

    database_path = tmp_path / "partial-username-unique.db"
    initialize_database(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys=OFF;
            CREATE TABLE users_replacement (
                id INTEGER NOT NULL PRIMARY KEY,
                role_id INTEGER NOT NULL,
                username VARCHAR(50) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(100) NOT NULL,
                is_active BOOLEAN NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(role_id) REFERENCES roles (id)
            );
            DROP TABLE users;
            ALTER TABLE users_replacement RENAME TO users;
            CREATE UNIQUE INDEX uq_users_username_active_only
                ON users(username) WHERE is_active = 1;
            """
        )

    target_engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(RuntimeError, match=r"users.*unique"):
            check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def test_local_verify_loads_database_guard_for_real_files_and_sidecars() -> None:
    """The one-command local gate must execute the shared DB guard."""
    project_root = Path(__file__).resolve().parents[1]
    script = (project_root / "scripts" / "verify.ps1").read_text(encoding="utf-8")
    guard = (project_root / "scripts" / "database_guard.ps1").read_text(
        encoding="utf-8"
    )

    assert "backend\\database\\parking.db" in script
    assert "database\\parking.db" in script
    assert "database_guard.ps1" in script
    assert "Get-FileHash" in guard
    assert '"-wal", "-shm", "-journal"' in guard
    assert "Assert-ProtectedDatabaseStateUnchanged" in script


@pytest.mark.skipif(os.name != "nt", reason="PowerShell integration gate runs on Windows")
def test_database_guard_detects_a_real_file_change(tmp_path: Path) -> None:
    """Exercise the PowerShell guard; string-presence tests can be false green."""
    project_root = Path(__file__).resolve().parents[1]
    helper = project_root / "scripts" / "database_guard.ps1"
    protected = tmp_path / "protected.db"
    protected.write_bytes(b"before")

    def ps_literal(path: Path) -> str:
        return str(path).replace("'", "''")

    command = (
        f". '{ps_literal(helper)}'; "
        f"$path = '{ps_literal(protected)}'; "
        "$before = Get-ProtectedDatabaseState @($path); "
        "[IO.File]::AppendAllText($path, 'changed'); "
        "$after = Get-ProtectedDatabaseState @($path); "
        "try { "
        "Assert-ProtectedDatabaseStateUnchanged -Before $before -After $after; "
        "exit 9 "
        "} catch { "
        "if ($_.Exception.Message -notmatch 'Verification.*DB/sidecar') { throw }; "
        "exit 0 "
        "}"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_ci_has_windows_release_safety_job() -> None:
    """Windows filesystem semantics are part of the rollout contract."""
    project_root = Path(__file__).resolve().parents[1]
    workflow = (project_root / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "windows-latest" in workflow
    assert "tests/test_release_safety.py" in workflow
