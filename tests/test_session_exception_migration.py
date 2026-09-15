"""The frozen PostgreSQL revision installs the same append-only event contract."""
import ast
from pathlib import Path

from core.session_event_guards import SESSION_EVENT_POSTGRES_GUARD_SQL, SESSION_EVENT_SQLITE_GUARDS


def test_frozen_exception_migration_matches_runtime_guards():
    path = Path(__file__).resolve().parents[1] / "backend/alembic/versions/20260915_02_session_exceptions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
    assert values["revision"] == "20260915_02" and values["down_revision"] == "20260915_01"
    assert values["SESSION_EVENT_SQLITE_GUARDS"] == SESSION_EVENT_SQLITE_GUARDS
    assert values["SESSION_EVENT_POSTGRES_GUARD_SQL"] == SESSION_EVENT_POSTGRES_GUARD_SQL
