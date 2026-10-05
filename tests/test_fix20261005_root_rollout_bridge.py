"""Review 05/10/2026 — SQLite schema10 upgrade bridge (root integration).

Migrations 20261005_11/12 corrected five SQLite backstop triggers. An existing
schema10 SQLite database still stores the previous definitions; db_rollout must
accept exactly those frozen texts, replace them with the current DDL, and keep
rejecting any other trigger body.
"""

import ast
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import db_rollout
from review_20261005_rollout import PRE_REVIEW_20261005_TRIGGER_SQL, _signature


VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "alembic" / "versions"


def _frozen(revision):
    path = next(VERSIONS.glob(revision + "_*.py"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"PREVIOUS_SQLITE_GUARDS", "SQLITE_GUARDS"}}


def _triggers(path):
    with closing(sqlite3.connect(path)) as connection:  # sqlite3's own context manager does not close
        return dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'").fetchall())


def test_bridge_equals_the_frozen_previous_guards_of_both_migrations():
    expected = {**_frozen("20261005_11")["PREVIOUS_SQLITE_GUARDS"], **_frozen("20261005_12")["PREVIOUS_SQLITE_GUARDS"]}
    assert PRE_REVIEW_20261005_TRIGGER_SQL == expected
    assert set(expected) == {"trg_declared_booking_source", "trg_declared_session_insert", "trg_declared_session_activate",
                             "trg_session_capacity_hold", "trg_payment_site_guard"}


def test_every_bridged_trigger_is_required_and_actually_changed():
    for name, old in PRE_REVIEW_20261005_TRIGGER_SQL.items():
        current = db_rollout._REQUIRED_TRIGGER_SQL[name]
        assert _signature(old) != _signature(current), name


def test_schema10_sqlite_upgrades_to_the_corrected_triggers(tmp_path):
    database = tmp_path / "schema10.db"
    db_rollout.initialize_database(database)
    current = {name: sql for name, sql in _triggers(database).items() if name in PRE_REVIEW_20261005_TRIGGER_SQL}
    assert set(current) == set(PRE_REVIEW_20261005_TRIGGER_SQL)
    with closing(sqlite3.connect(database)) as connection:  # simulate a database created before 05/10/2026
        for name, old in PRE_REVIEW_20261005_TRIGGER_SQL.items():
            connection.execute(f'DROP TRIGGER "{name}"')
            connection.execute(old)
        connection.commit()
    engine = db_rollout.create_engine(db_rollout._sqlite_url(database))
    try:
        with pytest.raises(RuntimeError):  # deep readiness still refuses the old contract
            db_rollout.verify_schema(engine)
    finally:
        engine.dispose()  # Windows: an open handle would block the atomic file replace

    db_rollout.initialize_database(database)

    upgraded = _triggers(database)
    for name in PRE_REVIEW_20261005_TRIGGER_SQL:
        assert _signature(upgraded[name]) == _signature(db_rollout._REQUIRED_TRIGGER_SQL[name]), name
        assert _signature(upgraded[name]) == _signature(current[name]), name


def test_unknown_trigger_body_is_still_rejected(tmp_path):
    database = tmp_path / "drifted.db"
    db_rollout.initialize_database(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute('DROP TRIGGER "trg_declared_session_insert"')
        connection.execute("CREATE TRIGGER trg_declared_session_insert BEFORE INSERT ON parking_sessions WHEN 0 BEGIN SELECT 1; END")
        connection.commit()
    with pytest.raises(RuntimeError, match="sai định nghĩa"):
        db_rollout.initialize_database(database)
