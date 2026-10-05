"""One-time, offline import from a cold SQLite database into PostgreSQL.

The command is deliberately conservative:

* the SQLite source is opened read-only and fingerprinted before/after;
* WAL/journal sidecars are rejected (stop the old backend first);
* the PostgreSQL schema must already be at the Alembic head and completely
  empty (the only row allowed is the placeholder default site that migration
  20260907_02 seeds into an empty database; it is replaced by the source's
  own sites);
* every table of the current schema is copied verbatim, parents before
  children, in one PostgreSQL transaction; business triggers are paused only
  while rows are copied (constraints and foreign keys stay on) and the deep
  business-invariant scan runs inside that transaction, so a failed import
  leaves the target empty instead of half-populated; and
* no other destination row is deleted or overwritten.

Usage (from ``backend``)::

    DATABASE_URL=postgresql+psycopg://... \
      python postgres_import.py --source /backup/parking.db \
      --confirm-empty-target
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, create_engine, func, null, select, text

from database import Base, _unicode_casefold
from db_rollout import check_database_readiness
import models  # noqa: F401 - populate Base.metadata (core and expansion tables)
from postgres_readiness import (
    _validate_business_invariants,
    _validate_catalog,
    check_postgres_readiness,
)


# The source gate only accepts a SQLite file at the CURRENT schema, so the copy
# must cover every current table. A fixed legacy subset silently dropped cards,
# receipts, shifts, sites and expansion data, and any monthly pass then failed
# the PostgreSQL card binding (#69, review 2026-10-05). Parents before children.
COPY_ORDER = tuple(table.name for table in Base.metadata.sorted_tables)

# Seeded by migration 20260907_02 into an empty database (LEGACY_SITE_BACKFILL_SQL).
_PLACEHOLDER_SITE_NAME = "Bãi xe mặc định"


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
    if isinstance(column.type, JSON):
        # SQLite keeps JSON as text. Re-binding that text through the JSON type
        # would store a JSON *string*; keep SQL NULL and JSON null distinct.
        if value is None:
            return null()
        parsed = json.loads(value) if isinstance(value, (str, bytes)) else value
        return JSON.NULL if parsed is None else parsed
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
    # Some tables are keyed by another column or a composite key (no ``id``).
    order = ", ".join(f'"{column.name}"' for column in table.primary_key.columns)
    rows = source_connection.execute(
        f'SELECT * FROM "{table_name}" ORDER BY {order}'
    ).fetchall()
    return [
        {
            column.name: _convert_value(column, row[column.name])
            for column in table.columns
        }
        for row in rows
    ]


def _assert_empty_destination(connection) -> list[int]:
    """Return the ids of the Alembic placeholder site; refuse any other data."""
    populated = []
    for table_name in COPY_ORDER:
        if table_name == "parking_sites":
            continue
        table = Base.metadata.tables[table_name]
        if connection.execute(select(func.count()).select_from(table)).scalar_one():
            populated.append(table_name)
    sites = Base.metadata.tables["parking_sites"]
    seeded = connection.execute(
        select(sites.c.id, sites.c.name, sites.c.address)
    ).all()
    placeholder = [
        row.id for row in seeded
        if row.name == _PLACEHOLDER_SITE_NAME and not row.address
    ]
    if len(seeded) > 1 or len(placeholder) != len(seeded):
        populated.append("parking_sites")
    if populated:
        raise RuntimeError(
            "PostgreSQL đích không rỗng; import từ chối ghi đè: "
            f"{populated}"
        )
    return placeholder


def _set_user_triggers(connection, enabled: bool) -> None:
    # Copying an already validated snapshot verbatim: business triggers would
    # re-judge historical rows against the current clock/state. Constraints,
    # unique indexes and FK (system) triggers stay active; the deep invariant
    # scan below re-checks cross-table rules before commit. ALTER TABLE is
    # transactional, so a rollback restores the triggers as well.
    action = "ENABLE" if enabled else "DISABLE"
    for table_name in COPY_ORDER:
        connection.execute(text(f"ALTER TABLE {table_name} {action} TRIGGER USER"))


def _has_serial_id(table) -> bool:
    key = list(table.primary_key.columns)
    return len(key) == 1 and key[0].name == "id" and isinstance(key[0].type, Integer)


def _reset_sequence(connection, table_name: str) -> None:
    # All names come from the fixed COPY_ORDER allow-list, never user input.
    # pg_get_serial_sequence is NULL for an id without a sequence (no-op).
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
                placeholder_sites = _assert_empty_destination(destination)

                # Reconstituting valid history can reference passes, holds or
                # links that have since ended; see _set_user_triggers.
                _set_user_triggers(destination, enabled=False)
                if placeholder_sites:
                    sites = Base.metadata.tables["parking_sites"]
                    destination.execute(
                        sites.delete().where(sites.c.id.in_(placeholder_sites))
                    )
                for table_name in COPY_ORDER:
                    rows = _read_rows(source_connection, table_name)
                    table = Base.metadata.tables[table_name]
                    if rows:
                        for offset in range(0, len(rows), 1000):
                            destination.execute(
                                table.insert(), rows[offset : offset + 1000]
                            )
                    counts[table_name] = len(rows)
                _set_user_triggers(destination, enabled=True)

                for table_name in COPY_ORDER:
                    if _has_serial_id(Base.metadata.tables[table_name]):
                        _reset_sequence(destination, table_name)

                # Validate before COMMIT: a violation rolls the whole import back
                # instead of leaving a partly filled target that every retry
                # refuses as non-empty.
                _validate_catalog(destination)
                _validate_business_invariants(destination)

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
