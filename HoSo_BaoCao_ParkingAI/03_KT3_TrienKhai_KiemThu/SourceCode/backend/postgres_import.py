"""One-time, offline import from a cold SQLite database into PostgreSQL.

The command is deliberately conservative:

* the SQLite source is opened read-only and fingerprinted before/after;
* WAL/journal sidecars are rejected (stop the old backend first);
* the PostgreSQL schema must already be at the Alembic head and completely
  empty;
* all rows are copied in one PostgreSQL transaction; and
* no destination row is deleted or overwritten.

Usage (from ``backend``)::

    DATABASE_URL=postgresql+psycopg://... \
      python postgres_import.py --source /backup/parking.db \
      --confirm-empty-target
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Boolean, Date, DateTime, create_engine, func, select, text

from database import Base, _unicode_casefold
from db_rollout import check_database_readiness
import models  # noqa: F401 - populate Base.metadata
from postgres_readiness import check_postgres_readiness


COPY_ORDER = (
    "roles",
    "vehicle_types",
    "customers",
    "zones",
    "users",
    "parking_slots",
    "vehicles",
    "price_configs",
    "monthly_passes",
    "parking_sessions",
    "ai_reports",
    "audit_logs",
)


def _digest(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return stat.st_size, stat.st_mtime_ns, hasher.hexdigest()


def _assert_cold_source(source: Path) -> tuple[int, int, str]:
    if not source.is_file():
        raise FileNotFoundError(source)
    sidecars = [
        Path(f"{source}{suffix}")
        for suffix in ("-wal", "-shm", "-journal")
        if Path(f"{source}{suffix}").exists()
    ]
    if sidecars:
        raise RuntimeError(
            "SQLite nguồn còn sidecar đang hoạt động; hãy dừng backend và "
            f"checkpoint trước: {[item.name for item in sidecars]}"
        )
    return _digest(source)


def _readonly_sqlite_connection(source: Path):
    connection = sqlite3.connect(
        f"{source.as_uri()}?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.create_function(
        "unicode_casefold", 1, _unicode_casefold, deterministic=True
    )
    connection.execute("PRAGMA query_only=ON")
    return connection


def _convert_value(column, value):
    if value is None:
        return None
    if isinstance(column.type, Boolean):
        return bool(value)
    if isinstance(column.type, DateTime) and not isinstance(value, datetime):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    if isinstance(column.type, Date) and not isinstance(value, date):
        return date.fromisoformat(str(value))
    return value


def _read_rows(source_connection, table_name: str) -> list[dict]:
    table = Base.metadata.tables[table_name]
    rows = source_connection.execute(
        f'SELECT * FROM "{table_name}" ORDER BY id'
    ).fetchall()
    return [
        {
            column.name: _convert_value(column, row[column.name])
            for column in table.columns
        }
        for row in rows
    ]


def _assert_empty_destination(connection) -> None:
    populated = []
    for table_name in COPY_ORDER:
        table = Base.metadata.tables[table_name]
        if connection.execute(select(func.count()).select_from(table)).scalar_one():
            populated.append(table_name)
    if populated:
        raise RuntimeError(
            "PostgreSQL đích không rỗng; import từ chối ghi đè: "
            f"{populated}"
        )


def _reset_sequence(connection, table_name: str) -> None:
    # All names come from the fixed COPY_ORDER allow-list, never user input.
    connection.execute(
        text(
            "SELECT setval("
            f"pg_get_serial_sequence('{table_name}', 'id')::regclass, "
            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table_name}"
        )
    )


def import_sqlite_to_postgres(source: Path, destination_url: str) -> dict[str, int]:
    source = source.resolve()
    source_fingerprint = _assert_cold_source(source)

    source_engine = create_engine(
        "sqlite://", creator=lambda: _readonly_sqlite_connection(source)
    )
    destination_engine = create_engine(destination_url, pool_pre_ping=True)
    if destination_engine.url.get_backend_name() != "postgresql":
        source_engine.dispose()
        destination_engine.dispose()
        raise RuntimeError("DATABASE_URL đích phải là PostgreSQL")

    try:
        check_database_readiness(source_engine, deep=True)
        check_postgres_readiness(destination_engine, deep=False)
        counts: dict[str, int] = {}

        with closing(_readonly_sqlite_connection(source)) as source_connection:
            # Hold one read transaction for the entire snapshot. A writer can
            # no longer commit unnoticed between two tables; any journal
            # sidecar/change also aborts the destination transaction below.
            source_connection.execute("BEGIN")
            with destination_engine.begin() as destination:
                # Prevent an application instance from racing the one-time import.
                destination.execute(
                    text(
                        "LOCK TABLE "
                        + ", ".join(COPY_ORDER)
                        + " IN ACCESS EXCLUSIVE MODE"
                    )
                )
                _assert_empty_destination(destination)

                for table_name in COPY_ORDER:
                    rows = _read_rows(source_connection, table_name)
                    table = Base.metadata.tables[table_name]
                    if table_name == "parking_sessions":
                        # Reconstituting valid history can reference a pass that
                        # has since been deactivated. Constraints/FKs remain on;
                        # only the insert-time business trigger is paused.
                        destination.execute(
                            text(
                                "ALTER TABLE parking_sessions "
                                "DISABLE TRIGGER USER"
                            )
                        )
                    if rows:
                        for offset in range(0, len(rows), 1000):
                            destination.execute(
                                table.insert(), rows[offset : offset + 1000]
                            )
                    if table_name == "parking_sessions":
                        destination.execute(
                            text(
                                "ALTER TABLE parking_sessions "
                                "ENABLE TRIGGER USER"
                            )
                        )
                    counts[table_name] = len(rows)

                for table_name in COPY_ORDER:
                    if table_name != "parking_sessions":
                        _reset_sequence(destination, table_name)

                if _digest(source) != source_fingerprint:
                    raise RuntimeError("SQLite nguồn thay đổi trong lúc import")
                _assert_cold_source(source)
            source_connection.rollback()

        if _digest(source) != source_fingerprint:
            raise RuntimeError("SQLite nguồn thay đổi ngay sau transaction import")
        check_postgres_readiness(destination_engine, deep=True)
        return counts
    finally:
        source_engine.dispose()
        destination_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import offline SQLite ParkingAI vào PostgreSQL rỗng"
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--confirm-empty-target",
        action="store_true",
        help="Xác nhận đã backup và PostgreSQL đích phải hoàn toàn rỗng",
    )
    args = parser.parse_args()
    if not args.confirm_empty_target:
        raise SystemExit("Thiếu --confirm-empty-target")

    destination_url = os.getenv("DATABASE_URL", "").strip()
    if not destination_url:
        raise SystemExit("Thiếu DATABASE_URL PostgreSQL trong environment")

    counts = import_sqlite_to_postgres(args.source, destination_url)
    print("Import PostgreSQL hoàn tất (số bản ghi theo bảng):")
    for table_name, count in counts.items():
        print(f"- {table_name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
