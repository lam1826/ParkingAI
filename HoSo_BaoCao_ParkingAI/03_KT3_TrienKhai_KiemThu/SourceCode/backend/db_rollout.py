"""Công cụ rollout SQLite tường minh, ưu tiên migrate trên bản sao.

Không module nào gọi các hàm này khi import app. Người vận hành phải chỉ rõ
đường dẫn đích; chế độ ``--copy-to`` dùng SQLite Backup API để giữ database
nguồn bất biến rồi chỉ migration bản sao.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from sqlalchemy import UniqueConstraint, create_engine, inspect as sqlalchemy_inspect

from database import (
    BOOLEAN_DOMAIN_COLUMNS,
    BOOLEAN_DOMAIN_TRIGGER_SQL,
    MONTHLY_PASS_DATE_RANGE_INSERT_TRIGGER_SQL,
    MONTHLY_PASS_DATE_RANGE_UPDATE_TRIGGER_SQL,
    MONTHLY_PASS_HISTORY_IMMUTABLE_TRIGGER_SQL,
    MONTHLY_PASS_PRICE_INSERT_TRIGGER_SQL,
    MONTHLY_PASS_PRICE_UPDATE_TRIGGER_SQL,
    PARKING_FEE_INTEGER_INSERT_TRIGGER_SQL,
    PARKING_FEE_INTEGER_UPDATE_TRIGGER_SQL,
    PARKING_FEE_SAFE_VND_INSERT_TRIGGER_SQL,
    PARKING_FEE_SAFE_VND_UPDATE_TRIGGER_SQL,
    PARKING_SLOT_ZONE_IMMUTABLE_TRIGGER_SQL,
    PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL,
    PRICE_INTEGER_INSERT_TRIGGER_SQL,
    PRICE_INTEGER_UPDATE_TRIGGER_SQL,
    PRICE_ACTIVE_SESSION_DELETE_GUARD_TRIGGER_SQL,
    PRICE_ACTIVE_SESSION_REPLACE_GUARD_TRIGGER_SQL,
    PRICE_ACTIVE_SESSION_UPDATE_GUARD_TRIGGER_SQL,
    PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL,
    PRICE_EFFECTIVE_DATE_UPDATE_TRIGGER_SQL,
    PRICE_SAFE_VND_INSERT_TRIGGER_SQL,
    PRICE_SAFE_VND_UPDATE_TRIGGER_SQL,
    PRICE_TICKET_TYPE_INSERT_TRIGGER_SQL,
    PRICE_TICKET_TYPE_UPDATE_TRIGGER_SQL,
    SESSION_COMPLETED_BILLING_IMMUTABLE_TRIGGER_SQL,
    SESSION_COMPLETED_STATUS_TERMINAL_TRIGGER_SQL,
    SESSION_DATETIME_INSERT_VALIDATION_TRIGGER_SQL,
    SESSION_DATETIME_UPDATE_VALIDATION_TRIGGER_SQL,
    SESSION_IDENTITY_IMMUTABLE_TRIGGER_SQL,
    SESSION_MONTHLY_PASS_INSERT_VALIDATION_TRIGGER_SQL,
    SESSION_RATE_ACTIVATION_VALIDATION_TRIGGER_SQL,
    SESSION_RATE_INSERT_VALIDATION_TRIGGER_SQL,
    SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION_TRIGGER_SQL,
    SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL,
    SESSION_STATE_INSERT_VALIDATION_TRIGGER_SQL,
    SESSION_STATE_UPDATE_VALIDATION_TRIGGER_SQL,
    SESSION_STATUS_INSERT_VALIDATION_TRIGGER_SQL,
    SESSION_STATUS_UPDATE_VALIDATION_TRIGGER_SQL,
    TRG_MONTHLY_PASS_DATE_RANGE_INSERT,
    TRG_MONTHLY_PASS_DATE_RANGE_UPDATE,
    TRG_MONTHLY_PASS_HISTORY_IMMUTABLE,
    TRG_MONTHLY_PASS_PRICE_INSERT,
    TRG_MONTHLY_PASS_PRICE_UPDATE,
    TRG_PARKING_FEE_INTEGER_INSERT,
    TRG_PARKING_FEE_INTEGER_UPDATE,
    TRG_PARKING_FEE_SAFE_VND_INSERT,
    TRG_PARKING_FEE_SAFE_VND_UPDATE,
    TRG_PARKING_SLOT_ZONE_IMMUTABLE_WITH_HISTORY,
    TRG_PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD,
    TRG_PRICE_INTEGER_INSERT,
    TRG_PRICE_INTEGER_UPDATE,
    TRG_PRICE_ACTIVE_SESSION_DELETE_GUARD,
    TRG_PRICE_ACTIVE_SESSION_REPLACE_GUARD,
    TRG_PRICE_ACTIVE_SESSION_UPDATE_GUARD,
    TRG_PRICE_EFFECTIVE_DATE_INSERT,
    TRG_PRICE_EFFECTIVE_DATE_UPDATE,
    TRG_PRICE_SAFE_VND_INSERT,
    TRG_PRICE_SAFE_VND_UPDATE,
    TRG_PRICE_TICKET_TYPE_INSERT,
    TRG_PRICE_TICKET_TYPE_UPDATE,
    TRG_SESSION_COMPLETED_BILLING_IMMUTABLE,
    TRG_SESSION_COMPLETED_STATUS_TERMINAL,
    TRG_SESSION_DATETIME_INSERT_VALIDATION,
    TRG_SESSION_DATETIME_UPDATE_VALIDATION,
    TRG_SESSION_IDENTITY_IMMUTABLE,
    TRG_SESSION_MONTHLY_PASS_INSERT_VALIDATION,
    TRG_SESSION_RATE_ACTIVATION_VALIDATION,
    TRG_SESSION_RATE_INSERT_VALIDATION,
    TRG_SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION,
    TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION,
    TRG_SESSION_STATE_INSERT_VALIDATION,
    TRG_SESSION_STATE_UPDATE_VALIDATION,
    TRG_SESSION_STATUS_INSERT_VALIDATION,
    TRG_SESSION_STATUS_UPDATE_VALIDATION,
    TRG_VEHICLE_LICENSE_PLATE_IMMUTABLE_WITH_HISTORY,
    TRG_VEHICLE_TYPE_IMMUTABLE_WITH_HISTORY,
    TRG_ZONE_CAPACITY_INTEGER_INSERT,
    TRG_ZONE_CAPACITY_INTEGER_UPDATE,
    TRG_ZONES_OPERATIONAL_UPDATE_GUARD,
    UQ_CUSTOMERS_PHONE_NORMALIZED,
    UQ_ROLES_NAME,
    VEHICLE_TYPE_IMMUTABLE_TRIGGER_SQL,
    VEHICLE_LICENSE_PLATE_IMMUTABLE_TRIGGER_SQL,
    ZONE_CAPACITY_INTEGER_INSERT_TRIGGER_SQL,
    ZONE_CAPACITY_INTEGER_UPDATE_TRIGGER_SQL,
    ZONES_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL,
    _unicode_casefold,
    _sqlite_datetime_invalid,
    run_sqlite_migrations,
)
from models import Base


_REQUIRED_TRIGGER_SQL = {
    "trg_parking_slots_capacity_insert": (
        "CREATE TRIGGER trg_parking_slots_capacity_insert "
        "BEFORE INSERT ON parking_slots FOR EACH ROW "
        "WHEN (SELECT COUNT(*) FROM parking_slots WHERE zone_id = NEW.zone_id) >= "
        "COALESCE((SELECT capacity FROM zones WHERE id = NEW.zone_id), 0) "
        "BEGIN SELECT RAISE(ABORT, 'zone capacity exceeded'); END"
    ),
    "trg_parking_slots_capacity_move": (
        "CREATE TRIGGER trg_parking_slots_capacity_move "
        "BEFORE UPDATE OF zone_id ON parking_slots FOR EACH ROW "
        "WHEN NEW.zone_id != OLD.zone_id AND "
        "(SELECT COUNT(*) FROM parking_slots WHERE zone_id = NEW.zone_id) >= "
        "COALESCE((SELECT capacity FROM zones WHERE id = NEW.zone_id), 0) "
        "BEGIN SELECT RAISE(ABORT, 'zone capacity exceeded'); END"
    ),
    "trg_zones_capacity_update": (
        "CREATE TRIGGER trg_zones_capacity_update "
        "BEFORE UPDATE OF capacity ON zones FOR EACH ROW "
        "WHEN NEW.capacity < (SELECT COUNT(*) FROM parking_slots "
        "WHERE zone_id = OLD.id) "
        "BEGIN SELECT RAISE(ABORT, 'zone capacity below slot count'); END"
    ),
    "trg_monthly_passes_no_overlap_insert": (
        "CREATE TRIGGER trg_monthly_passes_no_overlap_insert "
        "BEFORE INSERT ON monthly_passes FOR EACH ROW "
        "WHEN NEW.is_active = 1 AND EXISTS (SELECT 1 FROM monthly_passes "
        "WHERE vehicle_id = NEW.vehicle_id AND is_active = 1 "
        "AND start_date <= NEW.end_date AND end_date >= NEW.start_date) "
        "BEGIN SELECT RAISE(ABORT, 'monthly pass interval overlap'); END"
    ),
    "trg_monthly_passes_no_overlap_update": (
        "CREATE TRIGGER trg_monthly_passes_no_overlap_update "
        "BEFORE UPDATE OF vehicle_id, start_date, end_date, is_active "
        "ON monthly_passes FOR EACH ROW "
        "WHEN NEW.is_active = 1 AND EXISTS (SELECT 1 FROM monthly_passes "
        "WHERE id != OLD.id AND vehicle_id = NEW.vehicle_id AND is_active = 1 "
        "AND start_date <= NEW.end_date AND end_date >= NEW.start_date) "
        "BEGIN SELECT RAISE(ABORT, 'monthly pass interval overlap'); END"
    ),
    TRG_VEHICLE_TYPE_IMMUTABLE_WITH_HISTORY: VEHICLE_TYPE_IMMUTABLE_TRIGGER_SQL,
    TRG_VEHICLE_LICENSE_PLATE_IMMUTABLE_WITH_HISTORY: (
        VEHICLE_LICENSE_PLATE_IMMUTABLE_TRIGGER_SQL
    ),
    TRG_MONTHLY_PASS_HISTORY_IMMUTABLE: MONTHLY_PASS_HISTORY_IMMUTABLE_TRIGGER_SQL,
    TRG_MONTHLY_PASS_PRICE_INSERT: MONTHLY_PASS_PRICE_INSERT_TRIGGER_SQL,
    TRG_MONTHLY_PASS_PRICE_UPDATE: MONTHLY_PASS_PRICE_UPDATE_TRIGGER_SQL,
    TRG_MONTHLY_PASS_DATE_RANGE_INSERT: MONTHLY_PASS_DATE_RANGE_INSERT_TRIGGER_SQL,
    TRG_MONTHLY_PASS_DATE_RANGE_UPDATE: MONTHLY_PASS_DATE_RANGE_UPDATE_TRIGGER_SQL,
    TRG_PRICE_INTEGER_INSERT: PRICE_INTEGER_INSERT_TRIGGER_SQL,
    TRG_PRICE_INTEGER_UPDATE: PRICE_INTEGER_UPDATE_TRIGGER_SQL,
    TRG_PRICE_SAFE_VND_INSERT: PRICE_SAFE_VND_INSERT_TRIGGER_SQL,
    TRG_PRICE_SAFE_VND_UPDATE: PRICE_SAFE_VND_UPDATE_TRIGGER_SQL,
    TRG_PRICE_TICKET_TYPE_INSERT: PRICE_TICKET_TYPE_INSERT_TRIGGER_SQL,
    TRG_PRICE_TICKET_TYPE_UPDATE: PRICE_TICKET_TYPE_UPDATE_TRIGGER_SQL,
    TRG_PRICE_EFFECTIVE_DATE_INSERT: PRICE_EFFECTIVE_DATE_INSERT_TRIGGER_SQL,
    TRG_PRICE_EFFECTIVE_DATE_UPDATE: PRICE_EFFECTIVE_DATE_UPDATE_TRIGGER_SQL,
    TRG_PRICE_ACTIVE_SESSION_UPDATE_GUARD: (
        PRICE_ACTIVE_SESSION_UPDATE_GUARD_TRIGGER_SQL
    ),
    TRG_PRICE_ACTIVE_SESSION_DELETE_GUARD: (
        PRICE_ACTIVE_SESSION_DELETE_GUARD_TRIGGER_SQL
    ),
    TRG_PRICE_ACTIVE_SESSION_REPLACE_GUARD: (
        PRICE_ACTIVE_SESSION_REPLACE_GUARD_TRIGGER_SQL
    ),
    TRG_PARKING_FEE_INTEGER_INSERT: PARKING_FEE_INTEGER_INSERT_TRIGGER_SQL,
    TRG_PARKING_FEE_INTEGER_UPDATE: PARKING_FEE_INTEGER_UPDATE_TRIGGER_SQL,
    TRG_PARKING_FEE_SAFE_VND_INSERT: PARKING_FEE_SAFE_VND_INSERT_TRIGGER_SQL,
    TRG_PARKING_FEE_SAFE_VND_UPDATE: PARKING_FEE_SAFE_VND_UPDATE_TRIGGER_SQL,
    TRG_ZONE_CAPACITY_INTEGER_INSERT: ZONE_CAPACITY_INTEGER_INSERT_TRIGGER_SQL,
    TRG_ZONE_CAPACITY_INTEGER_UPDATE: ZONE_CAPACITY_INTEGER_UPDATE_TRIGGER_SQL,
    TRG_ZONES_OPERATIONAL_UPDATE_GUARD: ZONES_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL,
    TRG_PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD: (
        PARKING_SLOTS_OPERATIONAL_UPDATE_GUARD_TRIGGER_SQL
    ),
    TRG_PARKING_SLOT_ZONE_IMMUTABLE_WITH_HISTORY: (
        PARKING_SLOT_ZONE_IMMUTABLE_TRIGGER_SQL
    ),
    TRG_SESSION_MONTHLY_PASS_INSERT_VALIDATION: (
        SESSION_MONTHLY_PASS_INSERT_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_RATE_INSERT_VALIDATION: (
        SESSION_RATE_INSERT_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_RATE_ACTIVATION_VALIDATION: (
        SESSION_RATE_ACTIVATION_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_SLOT_ADMISSION_INSERT_VALIDATION: (
        SESSION_SLOT_ADMISSION_INSERT_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION: (
        SESSION_SLOT_ADMISSION_ACTIVATION_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_IDENTITY_IMMUTABLE: SESSION_IDENTITY_IMMUTABLE_TRIGGER_SQL,
    TRG_SESSION_COMPLETED_STATUS_TERMINAL: (
        SESSION_COMPLETED_STATUS_TERMINAL_TRIGGER_SQL
    ),
    TRG_SESSION_COMPLETED_BILLING_IMMUTABLE: (
        SESSION_COMPLETED_BILLING_IMMUTABLE_TRIGGER_SQL
    ),
    TRG_SESSION_STATUS_INSERT_VALIDATION: (
        SESSION_STATUS_INSERT_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_STATUS_UPDATE_VALIDATION: (
        SESSION_STATUS_UPDATE_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_DATETIME_INSERT_VALIDATION: (
        SESSION_DATETIME_INSERT_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_DATETIME_UPDATE_VALIDATION: (
        SESSION_DATETIME_UPDATE_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_STATE_INSERT_VALIDATION: (
        SESSION_STATE_INSERT_VALIDATION_TRIGGER_SQL
    ),
    TRG_SESSION_STATE_UPDATE_VALIDATION: (
        SESSION_STATE_UPDATE_VALIDATION_TRIGGER_SQL
    ),
}
_REQUIRED_TRIGGER_SQL.update(BOOLEAN_DOMAIN_TRIGGER_SQL)

_REQUIRED_INDEX_SQL = {
    UQ_ROLES_NAME: f"CREATE UNIQUE INDEX {UQ_ROLES_NAME} ON roles(name)",
    "ix_monthly_passes_pass_code": (
        "CREATE UNIQUE INDEX ix_monthly_passes_pass_code "
        "ON monthly_passes(pass_code) WHERE pass_code IS NOT NULL"
    ),
    "uq_price_config_one_active_per_vehicle_type": (
        "CREATE UNIQUE INDEX uq_price_config_one_active_per_vehicle_type "
        "ON price_configs(vehicle_type_id) WHERE is_active = 1"
    ),
    "uq_zones_name_normalized": (
        "CREATE UNIQUE INDEX uq_zones_name_normalized "
        "ON zones(unicode_casefold(name))"
    ),
    "uq_parking_slots_name_normalized": (
        "CREATE UNIQUE INDEX uq_parking_slots_name_normalized "
        "ON parking_slots(unicode_casefold(slot_name))"
    ),
    "uq_parking_session_one_active_per_vehicle": (
        "CREATE UNIQUE INDEX uq_parking_session_one_active_per_vehicle "
        "ON parking_sessions(vehicle_id) WHERE status = 'active'"
    ),
    "uq_parking_session_one_active_per_slot": (
        "CREATE UNIQUE INDEX uq_parking_session_one_active_per_slot "
        "ON parking_sessions(parking_slot_id) "
        "WHERE status = 'active' AND parking_slot_id IS NOT NULL"
    ),
    UQ_CUSTOMERS_PHONE_NORMALIZED: (
        f"CREATE UNIQUE INDEX {UQ_CUSTOMERS_PHONE_NORMALIZED} "
        "ON customers(unicode_casefold(phone_number))"
    ),
}

# Hai cột tiền tệ này từng được khai báo FLOAT trong schema legacy. Trigger
# insert/update hiện khóa giá trị ở số nguyên VND, nên rollout additive chấp
# nhận đúng hai type cũ này thay vì rebuild bảng và mạo hiểm dữ liệu.
_LEGACY_TYPE_COMPATIBILITY = {
    ("price_configs", "price"): {"INTEGER", "FLOAT"},
    ("parking_sessions", "parking_fee"): {"INTEGER", "FLOAT"},
}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_sidecars(path: Path) -> tuple[Path, ...]:
    return tuple(
        candidate
        for candidate in (
            Path(f"{path}-wal"),
            Path(f"{path}-shm"),
            Path(f"{path}-journal"),
        )
        if candidate.exists()
    )


def _file_fingerprint(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, _hash_file(path)


def _source_family_fingerprint(path: Path) -> dict[str, tuple[int, int, str]]:
    family = (path, *_sqlite_sidecars(path))
    return {member.name: _file_fingerprint(member) for member in family}


def _new_staging_path(output: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".partial",
        dir=output.parent,
    )
    os.close(descriptor)
    return Path(raw_path)


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _normalized_sql(sql: str | None) -> str:
    return " ".join((sql or "").lower().split())


def _ddl_signature(sql: str | None) -> str:
    """Canonical signature for the exact DDL contract stored by SQLite.

    SQLite may preserve ``IF NOT EXISTS`` and formatting differently between
    SQLAlchemy ``create_all`` and the additive migration. Neither changes the
    object definition, so only those two presentation details are ignored.
    """
    signature = "".join((sql or "").lower().split()).rstrip(";")
    return signature.replace("ifnotexists", "")


def _validate_index_definitions(definitions: dict[str, str], *, require_all: bool) -> None:
    for name, expected_sql in _REQUIRED_INDEX_SQL.items():
        definition = definitions.get(name)
        if not definition:
            if require_all:
                raise RuntimeError(f"Thiếu index schema bắt buộc: {name}")
            continue
        if _ddl_signature(definition) != _ddl_signature(expected_sql):
            raise RuntimeError(
                f"Index {name} tồn tại nhưng sai unique/cột/predicate"
            )


def _validate_trigger_definitions(definitions: dict[str, str], *, require_all: bool) -> None:
    for name, expected_sql in _REQUIRED_TRIGGER_SQL.items():
        definition = definitions.get(name)
        if not definition:
            if require_all:
                raise RuntimeError(f"Thiếu trigger schema bắt buộc: {name}")
            continue
        if _ddl_signature(definition) != _ddl_signature(expected_sql):
            raise RuntimeError(f"Trigger {name} tồn tại nhưng sai định nghĩa")


def _trigger_definitions(target_engine) -> dict[str, str]:
    with target_engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
        ).all()
    return {name: sql or "" for name, sql in rows}


def _index_definitions(target_engine) -> dict[str, str]:
    with target_engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'index' AND sql IS NOT NULL"
        ).all()
    return {name: sql or "" for name, sql in rows}


def _type_signature(column_type, dialect) -> str:
    return "".join(str(column_type.compile(dialect=dialect)).upper().split())


def _default_signature(value, dialect) -> str | None:
    """Normalize harmless SQLite formatting while preserving value semantics."""
    if value is None:
        return None
    compile_value = getattr(value, "compile", None)
    if callable(compile_value):
        rendered = str(
            compile_value(
                dialect=dialect,
                compile_kwargs={"literal_binds": True},
            )
        )
    else:
        rendered = str(value)

    signature = "".join(rendered.upper().split())
    # SQLite may reflect DEFAULT (CURRENT_TIMESTAMP) while SQLAlchemy emits
    # CURRENT_TIMESTAMP. Parentheses around the whole expression are cosmetic.
    while signature.startswith("(") and signature.endswith(")"):
        depth = 0
        encloses_whole_expression = True
        for index, character in enumerate(signature):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(signature) - 1:
                    encloses_whole_expression = False
                    break
        if not encloses_whole_expression or depth != 0:
            break
        signature = signature[1:-1]
    return signature


def _foreign_key_action(value: str | None) -> str:
    return " ".join((value or "NO ACTION").upper().split())


def _foreign_key_signature(
    constraint,
) -> tuple[tuple[str, ...], str, tuple[str, ...], str, str]:
    elements = tuple(constraint.elements)
    referred_tables = {element.column.table.name for element in elements}
    if len(referred_tables) != 1:
        raise RuntimeError("Foreign key nhiều bảng không được hỗ trợ trong schema contract")
    return (
        tuple(element.parent.name for element in elements),
        next(iter(referred_tables)),
        tuple(element.column.name for element in elements),
        _foreign_key_action(constraint.ondelete),
        _foreign_key_action(constraint.onupdate),
    )


def _unique_column_sets(target_engine, table_name: str) -> set[tuple[str, ...]]:
    """Reflect column-based UNIQUE constraints without expression-index warnings."""
    quote = target_engine.dialect.identifier_preparer.quote
    unique_columns: set[tuple[str, ...]] = set()
    with target_engine.connect() as connection:
        index_rows = connection.exec_driver_sql(
            f"PRAGMA index_list({quote(table_name)})"
        ).fetchall()
        for index_row in index_rows:
            # A partial unique index is not a full UNIQUE constraint.
            if not index_row[2] or index_row[4]:
                continue
            index_name = index_row[1]
            key_rows = tuple(
                row
                for row in connection.exec_driver_sql(
                    f"PRAGMA index_xinfo({quote(index_name)})"
                ).fetchall()
                if row[5]
            )
            columns = tuple(row[2] for row in key_rows)
            collations = tuple((row[4] or "BINARY").upper() for row in key_rows)
            if (
                columns
                and all(column is not None for column in columns)
                and all(collation == "BINARY" for collation in collations)
            ):
                unique_columns.add(columns)
    return unique_columns


def _foreign_key_sets(
    target_engine,
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...], str, str]]:
    """Read FK actions from PRAGMA; SQLAlchemy can miss multiline ON DELETE."""
    quote = target_engine.dialect.identifier_preparer.quote
    with target_engine.connect() as connection:
        rows = connection.exec_driver_sql(
            f"PRAGMA foreign_key_list({quote(table_name)})"
        ).fetchall()

    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row)

    result = set()
    for constraint_rows in grouped.values():
        ordered = sorted(constraint_rows, key=lambda row: row[1])
        result.add(
            (
                tuple(row[3] for row in ordered),
                ordered[0][2],
                tuple(row[4] for row in ordered),
                _foreign_key_action(ordered[0][6]),
                _foreign_key_action(ordered[0][5]),
            )
        )
    return result


def _validate_table_contract(target_engine) -> None:
    """Validate the ORM table contract that ``create_all`` cannot repair.

    Extra legacy columns are tolerated unless they are NOT NULL without a
    default (which would make normal ORM INSERT fail). Required columns, type,
    nullability, PK, unique constraints and FK definitions must match.
    """
    inspector = sqlalchemy_inspect(target_engine)
    actual_tables = set(inspector.get_table_names())

    for expected_table in Base.metadata.sorted_tables:
        table_name = expected_table.name
        if table_name not in actual_tables:
            raise RuntimeError(f"Thiếu bảng schema bắt buộc: {table_name}")

        actual_columns = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }
        expected_columns = {column.name: column for column in expected_table.columns}
        for column_name, expected_column in expected_columns.items():
            actual_column = actual_columns.get(column_name)
            qualified_name = f"{table_name}.{column_name}"
            if actual_column is None:
                raise RuntimeError(f"Thiếu cột schema bắt buộc: {qualified_name}")

            actual_type = _type_signature(actual_column["type"], target_engine.dialect)
            expected_type = _type_signature(expected_column.type, target_engine.dialect)
            allowed_types = _LEGACY_TYPE_COMPATIBILITY.get(
                (table_name, column_name),
                {expected_type},
            )
            if actual_type not in allowed_types:
                raise RuntimeError(
                    f"Cột {qualified_name} sai type contract: "
                    f"expected={sorted(allowed_types)}, actual={actual_type}"
                )

            # SQLite reports an implicit single-column INTEGER PRIMARY KEY as
            # nullable even though NULL inserts allocate a rowid. That narrow
            # exception does not apply to text/composite PKs, where omitting
            # NOT NULL genuinely permits NULL values.
            implicit_integer_primary_key = (
                expected_column.primary_key
                and len(expected_table.primary_key.columns) == 1
                and expected_type == "INTEGER"
            )
            if (
                not implicit_integer_primary_key
                and bool(actual_column["nullable"]) != bool(expected_column.nullable)
            ):
                raise RuntimeError(
                    f"Cột {qualified_name} sai nullable contract: "
                    f"expected={expected_column.nullable}, "
                    f"actual={actual_column['nullable']}"
                )

            if expected_column.server_default is not None:
                expected_default = _default_signature(
                    expected_column.server_default.arg,
                    target_engine.dialect,
                )
                actual_default = _default_signature(
                    actual_column.get("default"),
                    target_engine.dialect,
                )
                if actual_default != expected_default:
                    raise RuntimeError(
                        f"Cột {qualified_name} sai server default contract: "
                        f"expected={expected_default}, actual={actual_default}"
                    )

        actual_pk = tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
        expected_pk = tuple(column.name for column in expected_table.primary_key.columns)
        if actual_pk != expected_pk:
            raise RuntimeError(
                f"Bảng {table_name} sai primary key contract: "
                f"expected={expected_pk}, actual={actual_pk}"
            )

        actual_fks = _foreign_key_sets(target_engine, table_name)
        expected_fks = {
            _foreign_key_signature(constraint)
            for constraint in expected_table.foreign_key_constraints
        }
        if actual_fks != expected_fks:
            raise RuntimeError(
                f"Bảng {table_name} sai foreign key contract: "
                f"expected={sorted(expected_fks)}, actual={sorted(actual_fks)}"
            )

        actual_unique = _unique_column_sets(target_engine, table_name)
        expected_unique = {
            tuple(column.name for column in constraint.columns)
            for constraint in expected_table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        missing_unique = expected_unique - actual_unique
        if missing_unique:
            raise RuntimeError(
                f"Bảng {table_name} thiếu unique constraint bắt buộc: "
                f"{sorted(missing_unique)}"
            )

        actual_pk_names = set(actual_pk)
        blocking_extra_columns = sorted(
            column_name
            for column_name, column in actual_columns.items()
            if column_name not in expected_columns
            and column_name not in actual_pk_names
            and not column["nullable"]
            and column.get("default") is None
        )
        if blocking_extra_columns:
            raise RuntimeError(
                f"Bảng {table_name} có cột legacy NOT NULL không default làm "
                f"ORM insert thất bại: {blocking_extra_columns}"
            )


def verify_schema(target_engine) -> None:
    """Fail loudly nếu thiếu DB backstop hoặc definition bị stale."""
    _validate_table_contract(target_engine)
    _validate_index_definitions(
        _index_definitions(target_engine),
        require_all=True,
    )
    _validate_trigger_definitions(
        _trigger_definitions(target_engine),
        require_all=True,
    )


def _validate_business_invariants(connection) -> None:
    """Validate denormalized state that schema shape alone cannot express."""
    for table_name, boolean_columns in BOOLEAN_DOMAIN_COLUMNS.items():
        invalid_predicate = " OR ".join(
            f"{column} IS NULL OR typeof({column}) != 'integer' "
            f"OR {column} NOT IN (0, 1)"
            for column in boolean_columns
        )
        invalid_boolean = connection.exec_driver_sql(
            f"SELECT id, {', '.join(boolean_columns)} FROM {table_name} "
            f"WHERE {invalid_predicate} ORDER BY id LIMIT 1"
        ).first()
        if invalid_boolean:
            raise RuntimeError(
                f"Bất biến boolean 0/1 của {table_name} không hợp lệ: "
                f"{tuple(invalid_boolean)}"
            )

    invalid_session_lifecycle = connection.exec_driver_sql(
        "SELECT id, status, check_in_time, check_out_time, parking_fee, "
        "staff_out_id FROM parking_sessions WHERE "
        "status IS NULL OR status NOT IN ('active', 'completed', 'cancelled') "
        "OR (" + _sqlite_datetime_invalid("check_in_time") + ") "
        "OR (check_out_time IS NOT NULL AND ("
        + _sqlite_datetime_invalid("check_out_time")
        + ")) OR (status = 'completed' AND (check_out_time IS NULL "
        "OR parking_fee IS NULL OR staff_out_id IS NULL "
        "OR check_out_time < check_in_time)) "
        "OR (status = 'active' AND (check_out_time IS NOT NULL "
        "OR parking_fee IS NOT NULL OR staff_out_id IS NOT NULL)) "
        "ORDER BY id LIMIT 1"
    ).first()
    if invalid_session_lifecycle:
        raise RuntimeError(
            "Bất biến vòng đời parking_sessions không hợp lệ: "
            f"{tuple(invalid_session_lifecycle)}"
        )

    occupancy_drift = connection.exec_driver_sql(
        """
        SELECT
            parking_slots.id,
            parking_slots.is_occupied,
            CASE WHEN EXISTS (
                SELECT 1
                FROM parking_sessions
                WHERE parking_sessions.parking_slot_id = parking_slots.id
                  AND parking_sessions.status = 'active'
            ) THEN 1 ELSE 0 END AS expected_is_occupied
        FROM parking_slots
        WHERE parking_slots.is_occupied NOT IN (0, 1)
           OR parking_slots.is_occupied != CASE WHEN EXISTS (
                SELECT 1
                FROM parking_sessions
                WHERE parking_sessions.parking_slot_id = parking_slots.id
                  AND parking_sessions.status = 'active'
            ) THEN 1 ELSE 0 END
        ORDER BY parking_slots.id
        LIMIT 1
        """
    ).first()
    if occupancy_drift:
        slot_id, actual, expected = occupancy_drift
        raise RuntimeError(
            "Bất biến parking_slots.is_occupied không khớp phiên "
            "parking_sessions active: "
            f"slot_id={slot_id}, is_occupied={actual}, expected={expected}"
        )

    invalid_effective_date = connection.exec_driver_sql(
        """
        SELECT id, effective_date
        FROM price_configs
        WHERE effective_date IS NULL
           OR typeof(effective_date) != 'text'
           OR effective_date NOT GLOB
              '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
           OR substr(effective_date, 1, 4) = '0000'
           OR date(effective_date, '+0 days') IS NULL
           OR date(effective_date, '+0 days') != effective_date
        ORDER BY id
        LIMIT 1
        """
    ).first()
    if invalid_effective_date:
        raise RuntimeError(
            "Bất biến price_configs.effective_date không phải ngày "
            f"YYYY-MM-DD hợp lệ: {tuple(invalid_effective_date)}"
        )

    invalid_entitlement = connection.exec_driver_sql(
        """
        SELECT ps.id, ps.vehicle_id, ps.monthly_pass_id, ps.check_in_time
        FROM parking_sessions AS ps
        LEFT JOIN monthly_passes AS mp ON mp.id = ps.monthly_pass_id
        WHERE ps.monthly_pass_id IS NOT NULL
          AND (
              mp.id IS NULL
              OR mp.vehicle_id != ps.vehicle_id
              OR date(ps.check_in_time) IS NULL
              OR mp.start_date > date(ps.check_in_time)
              OR mp.end_date < date(ps.check_in_time)
          )
        ORDER BY ps.id
        LIMIT 1
        """
    ).first()
    if invalid_entitlement:
        raise RuntimeError(
            "Bất biến quyền lợi vé tháng của parking_sessions không hợp lệ: "
            f"session={tuple(invalid_entitlement)}"
        )

    missing_rate = connection.exec_driver_sql(
        """
        SELECT ps.id, ps.vehicle_id, ps.check_in_time
        FROM parking_sessions AS ps
        JOIN vehicles AS v ON v.id = ps.vehicle_id
        WHERE ps.status = 'active'
          AND NOT EXISTS (
              SELECT 1
              FROM price_configs AS pc
              WHERE pc.vehicle_type_id = v.vehicle_type_id
                AND pc.is_active = 1
                AND pc.effective_date <= date(ps.check_in_time)
          )
        ORDER BY ps.id
        LIMIT 1
        """
    ).first()
    if missing_rate:
        raise RuntimeError(
            "Bất biến bảng giá dự phòng của parking_sessions không hợp lệ: "
            f"phiên active thiếu bảng giá hiệu lực={tuple(missing_rate)}"
        )

    invalid_slot_admission = connection.exec_driver_sql(
        """
        SELECT ps.id, ps.vehicle_id, ps.parking_slot_id
        FROM parking_sessions AS ps
        JOIN vehicles AS v ON v.id = ps.vehicle_id
        LEFT JOIN parking_slots AS slot ON slot.id = ps.parking_slot_id
        LEFT JOIN zones AS z ON z.id = slot.zone_id
        WHERE ps.status = 'active'
          AND ps.parking_slot_id IS NOT NULL
          AND (
              slot.id IS NULL
              OR z.id IS NULL
              OR slot.vehicle_type_id != v.vehicle_type_id
              OR slot.is_active != 1
              OR z.is_active != 1
          )
        ORDER BY ps.id
        LIMIT 1
        """
    ).first()
    if invalid_slot_admission:
        raise RuntimeError(
            "Bất biến admission của parking_sessions/parking_slots không "
            "hợp lệ (loại xe hoặc trạng thái slot/zone): "
            f"session={tuple(invalid_slot_admission)}"
        )


def check_database_readiness(target_engine, *, deep: bool = True) -> None:
    """Read-only schema gate; explicit rollout may request deep integrity checks."""
    readiness_engine = target_engine
    dispose_readiness_engine = False
    if target_engine.url.get_backend_name() == "sqlite":
        database_name = target_engine.url.database
        if database_name and database_name != ":memory:":
            database_path = Path(database_name).resolve()
            if not database_path.is_file():
                raise RuntimeError("SQLite database chưa tồn tại")

            # Use an explicit mode=ro connection so a readiness probe can never
            # create a typo/missing DB or mutate schema/data.
            readonly_uri = f"{database_path.as_uri()}?mode=ro"

            def _readonly_connection():
                connection = sqlite3.connect(
                    readonly_uri,
                    uri=True,
                    check_same_thread=False,
                )
                connection.create_function(
                    "unicode_casefold",
                    1,
                    _unicode_casefold,
                    deterministic=True,
                )
                connection.execute("PRAGMA query_only=ON")
                return connection

            readiness_engine = create_engine(
                "sqlite://",
                creator=_readonly_connection,
            )
            dispose_readiness_engine = True

    try:
        verify_schema(readiness_engine)
        with readiness_engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1").scalar_one()
            _validate_business_invariants(connection)
            if not deep:
                return
            integrity = connection.exec_driver_sql(
                "PRAGMA integrity_check"
            ).scalar_one()
            if integrity != "ok":
                raise RuntimeError(f"SQLite integrity_check thất bại: {integrity}")
            foreign_key_errors = connection.exec_driver_sql(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if foreign_key_errors:
                raise RuntimeError(
                    "SQLite foreign_key_check thất bại: "
                    f"{foreign_key_errors}"
                )
    finally:
        if dispose_readiness_engine:
            readiness_engine.dispose()


def _initialize_candidate(target: Path) -> None:
    """Mutate only a disposable candidate; callers publish it atomically."""
    target_engine = create_engine(
        _sqlite_url(target),
        connect_args={"check_same_thread": False},
    )
    try:
        # Object cùng tên nhưng sai definition làm các câu IF NOT EXISTS no-op.
        # Chặn chúng trước mọi ALTER/CREATE để lỗi preflight không nâng DB dở.
        _validate_trigger_definitions(
            _trigger_definitions(target_engine),
            require_all=False,
        )
        _validate_index_definitions(
            _index_definitions(target_engine),
            require_all=False,
        )
        run_sqlite_migrations(target_engine)
        Base.metadata.create_all(bind=target_engine)
        verify_schema(target_engine)
        check_database_readiness(target_engine)
    finally:
        target_engine.dispose()


def _assert_cold_source(source: Path) -> None:
    sidecars = _sqlite_sidecars(source)
    if sidecars:
        names = ", ".join(path.name for path in sidecars)
        raise RuntimeError(
            "Database nguồn còn WAL/sidecar/journal đang hoạt động "
            f"({names}). Hãy dừng backend và checkpoint/đóng SQLite trước "
            "khi tạo bản sao rollout."
        )


def _assert_delete_journal_mode(
    source: Path,
    expected_fingerprint: dict[str, tuple[int, int, str]],
) -> None:
    """Reject a clean-looking file whose persistent mode still expects WAL.

    SQLite records the read/write format at header offsets 18/19 (1=rollback
    journal, 2=WAL). Reading those bytes avoids opening a connection that may
    itself create WAL/SHM files on Windows.
    """
    with source.open("rb") as stream:
        header = stream.read(20)
    _assert_source_unchanged(source, expected_fingerprint)
    if header.startswith(b"SQLite format 3\x00") and header[18:20] != b"\x01\x01":
        journal_mode = "WAL" if b"\x02" in header[18:20] else "UNKNOWN"
        raise RuntimeError(
            "Database nguồn phải dùng journal_mode=DELETE khi rollout; "
            f"phát hiện journal_mode={journal_mode}. Hãy dừng mọi writer, "
            "chạy PRAGMA wal_checkpoint(TRUNCATE) rồi "
            "PRAGMA journal_mode=DELETE trước khi thử lại."
        )


def _backup_cold_source(source: Path, staging: Path) -> dict[str, tuple[int, int, str]]:
    _assert_cold_source(source)
    source_fingerprint = _source_family_fingerprint(source)
    if set(source_fingerprint) != {source.name}:
        _assert_cold_source(source)
        raise RuntimeError("Database nguồn xuất hiện sidecar trong lúc preflight")
    _assert_delete_journal_mode(source, source_fingerprint)

    # Không dùng immutable=1: cờ đó có thể cố ý bỏ qua WAL vừa xuất hiện và
    # tạo một bản sao thiếu transaction đã commit. mode=ro vẫn không ghi nguồn
    # nhưng tuân theo locking/journal state của SQLite.
    source_uri = f"{source.as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        source_connection.create_function(
            "unicode_casefold",
            1,
            _unicode_casefold,
            deterministic=True,
        )
        if source_connection.execute("PRAGMA integrity_check").fetchone() != (
            "ok",
        ):
            raise RuntimeError("Database nguồn không vượt qua PRAGMA integrity_check")
        _assert_source_unchanged(source, source_fingerprint)
        with closing(sqlite3.connect(staging)) as output_connection:
            source_connection.backup(output_connection)
    _assert_source_unchanged(source, source_fingerprint)
    return source_fingerprint


def _assert_source_unchanged(
    source: Path,
    expected: dict[str, tuple[int, int, str]],
) -> None:
    if _source_family_fingerprint(source) != expected:
        raise RuntimeError(
            "Database nguồn hoặc WAL/sidecar/journal đã thay đổi trong "
            "lúc tạo/migrate bản sao"
        )


def _replace_file_windows(staging: Path, target: Path) -> None:
    """Atomically replace an existing file while retaining its Windows DACL.

    ``os.replace`` gives the replacement file the directory's inherited DACL,
    which can silently broaden or narrow access. Win32 ``ReplaceFileW`` keeps
    the replaced file's ACL and other mergeable filesystem metadata.
    """
    import ctypes
    from ctypes import wintypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    )
    replace_file.restype = wintypes.BOOL
    if not replace_file(str(target), str(staging), None, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def _replace_existing_file(staging: Path, target: Path) -> None:
    """Publish a candidate without discarding destination security metadata."""
    if os.name == "nt":
        _replace_file_windows(staging, target)
        return

    source_stat = target.stat(follow_symlinks=False)
    staging_stat = staging.stat(follow_symlinks=False)
    source_owner = (source_stat.st_uid, source_stat.st_gid)
    staging_owner = (staging_stat.st_uid, staging_stat.st_gid)
    if staging_owner != source_owner:
        # Fail loudly when the rollout account cannot retain ownership. Running
        # as the database owner avoids requiring elevated chown privileges.
        os.chown(staging, *source_owner, follow_symlinks=False)
    # chown may clear setuid/setgid bits, so mode must be applied afterwards.
    os.chmod(staging, source_stat.st_mode & 0o7777, follow_symlinks=False)
    os.replace(staging, target)


def initialize_database(database_path: str | Path) -> None:
    """Atomically create/upgrade the explicit SQLite target via a candidate."""
    target = Path(database_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not target.is_file():
        raise FileExistsError(target)

    staging = _new_staging_path(target)
    try:
        if target.exists():
            source_fingerprint = _backup_cold_source(target, staging)
            _initialize_candidate(staging)
            _assert_source_unchanged(target, source_fingerprint)
            _replace_existing_file(staging, target)
        else:
            _initialize_candidate(staging)
            # Atomic no-clobber publish for a new path.
            os.link(staging, target)
            staging.unlink()
    finally:
        staging.unlink(missing_ok=True)


def migrate_copy(source_path: str | Path, output_path: str | Path) -> Path:
    """Backup ``source`` sang file mới, rồi migration chỉ file mới đó.

    Hàm cố ý từ chối ghi đè để một lần gõ nhầm không phá bản backup/UAT đã có.
    Fingerprint DB + sidecar được kiểm tra lại; chỉ candidate vượt toàn bộ gate
    mới được publish atomic vào đường dẫn output.
    """
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    if source == output:
        raise ValueError("Database nguồn và bản sao migration phải là hai đường dẫn khác nhau")
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = _new_staging_path(output)
    try:
        source_fingerprint = _backup_cold_source(source, staging)
        _initialize_candidate(staging)
        _assert_source_unchanged(source, source_fingerprint)

        # Atomic no-clobber publication: hard-link creation fails if another
        # process created output after the initial exists() check. os.replace
        # is intentionally avoided because it may overwrite on both OS families.
        os.link(staging, output)
        staging.unlink()
        return output
    finally:
        staging.unlink(missing_ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rollout schema ParkingAI một cách tường minh")
    parser.add_argument("--database", type=Path, help="DB đích để migrate trực tiếp")
    parser.add_argument("--source", type=Path, help="DB nguồn chỉ đọc để tạo bản sao UAT")
    parser.add_argument("--copy-to", type=Path, help="File bản sao mới sẽ được migration")
    return parser


def _make_console_unicode_safe() -> None:
    """Không để console Windows hẹp làm rollout đã thành công trả exit 1.

    `PYTHONIOENCODING=cp1252:strict` và một workspace có tên tiếng Việt là
    đủ để `print()` ném UnicodeEncodeError. `backslashreplace` vẫn giữ đầy đủ
    thông tin đường dẫn theo dạng escape và hoạt động trên mọi TextIOWrapper.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")


def main() -> int:
    _make_console_unicode_safe()
    args = _build_parser().parse_args()
    copy_mode = args.source is not None or args.copy_to is not None
    if args.database and copy_mode:
        raise SystemExit("Chỉ chọn --database hoặc cặp --source/--copy-to")
    if args.database:
        initialize_database(args.database)
        print(f"Đã migration database: {args.database.resolve()}")
        return 0
    if args.source and args.copy_to:
        migrated = migrate_copy(args.source, args.copy_to)
        print(f"Đã tạo và migration bản sao: {migrated}")
        return 0
    raise SystemExit("Cần --database hoặc đầy đủ --source và --copy-to")


if __name__ == "__main__":
    raise SystemExit(main())
