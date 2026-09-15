"""Verify backup/restore of a marked synthetic DB without replacing its source."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4


def verify(source):
    source = source.resolve()
    marker = json.loads(Path(str(source) + ".demo.json").read_text(encoding="utf-8"))
    if marker.get("profile") != "single-lot-academic-v1" or not marker.get("synthetic_history"):
        raise ValueError("Only a marked single-lot synthetic database is accepted")
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from database import _unicode_casefold, create_database_engine
    from db_rollout import check_database_readiness

    directory = source.parent / ("recovery-" + uuid4().hex)
    directory.mkdir()
    backup, restored = directory / "backup.db", directory / "restored.db"
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as origin, sqlite3.connect(backup) as snapshot:
        origin.backup(snapshot)
    with sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True) as snapshot, sqlite3.connect(restored) as destination:
        snapshot.backup(destination)

    def digest(path):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            # Expression indexes use the same normalizer as application engines.
            connection.create_function("unicode_casefold", 1, _unicode_casefold, deterministic=True)
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            result = {}
            for (name,) in tables:
                rows = connection.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
                result[name] = (len(rows), hashlib.sha256(repr(sorted(map(repr, rows))).encode()).hexdigest())
            return result

    before, after = digest(backup), digest(restored)
    assert before == after, "Restored table data differs from the snapshot"
    engine = create_database_engine("sqlite:///" + restored.as_posix())
    try:
        check_database_readiness(engine)
    finally:
        engine.dispose()
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "result": "PASS", "tables_compared": len(before),
            "row_counts": {key: value[0] for key, value in before.items()}, "backup": str(backup), "restored": str(restored),
            "source_overwritten": False, "readiness": "PASS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "tables_compared": result["tables_compared"], "output": str(args.output)}))
