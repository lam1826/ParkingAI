"""Read-only readiness contract for the managed PostgreSQL deployment.

This module is the production-side counterpart of ``db_rollout.py``.  It owns
all PostgreSQL catalog knowledge and exposes one small seam used by ``/ready``
and deployment smoke checks.  It never creates, migrates, repairs, or locks
application rows.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine


POSTGRES_SCHEMA_REVISION = "20260828_01"

REQUIRED_TABLES = frozenset(
    {
        "roles",
        "users",
        "vehicle_types",
        "zones",
        "parking_slots",
        "customers",
        "vehicles",
        "monthly_passes",
        "price_configs",
        "parking_sessions",
        "ai_reports",
        "audit_logs",
    }
)

REQUIRED_INDEXES = frozenset(
    {
        "uq_roles_name",
        "uq_vehicle_types_name_normalized",
        "uq_customers_phone_normalized",
        "uq_zones_name_normalized",
        "uq_parking_slots_name_normalized",
        "uq_price_config_one_active_per_vehicle_type",
        "ix_monthly_passes_pass_code",
        "uq_parking_session_one_active_per_vehicle",
        "uq_parking_session_one_active_per_slot",
    }
)

REQUIRED_CONSTRAINTS = frozenset(
    {
        "ck_zones_capacity_nonnegative",
        "ck_price_configs_ticket_type",
        "ck_price_configs_exact_vnd",
        "ck_monthly_passes_exact_vnd",
        "ck_monthly_passes_date_range",
        "ex_monthly_passes_no_active_overlap",
        "ck_parking_sessions_status",
        "ck_parking_sessions_exact_vnd",
        "ck_parking_sessions_state",
    }
)

REQUIRED_TRIGGERS = frozenset(
    {
        "trg_vehicles_history_guard",
        "trg_monthly_passes_history_immutable",
        "trg_price_configs_active_session_update_guard",
        "trg_price_configs_active_session_delete_guard",
        "trg_zones_operational_update_guard",
        "trg_parking_slots_capacity_and_operation_guard",
        "trg_parking_sessions_validate",
    }
)


def _require_all(kind: str, actual: Iterable[str], expected: frozenset[str]) -> None:
    missing = sorted(expected - set(actual))
    if missing:
        raise RuntimeError(f"PostgreSQL thiếu {kind} bắt buộc: {missing}")


def _validate_catalog(connection) -> None:
    encoding = connection.execute(text("SHOW server_encoding")).scalar_one()
    if encoding != "UTF8":
        raise RuntimeError(
            f"PostgreSQL server_encoding phải là UTF8, actual={encoding}"
        )

    revision = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one()
    if not revision:
        raise RuntimeError("PostgreSQL alembic_version trống")

    tables = connection.execute(
        text(
            "SELECT tablename FROM pg_catalog.pg_tables "
            "WHERE schemaname = current_schema()"
        )
    ).scalars()
    _require_all("bảng", tables, REQUIRED_TABLES)

    indexes = connection.execute(
        text(
            "SELECT indexname FROM pg_catalog.pg_indexes "
            "WHERE schemaname = current_schema()"
        )
    ).scalars()
    _require_all("index", indexes, REQUIRED_INDEXES)

    constraints = connection.execute(
        text(
            "SELECT con.conname FROM pg_catalog.pg_constraint con "
            "JOIN pg_catalog.pg_namespace n ON n.oid = con.connamespace "
            "WHERE n.nspname = current_schema()"
        )
    ).scalars()
    _require_all("constraint", constraints, REQUIRED_CONSTRAINTS)

    triggers = connection.execute(
        text(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE trigger_schema = current_schema()"
        )
    ).scalars()
    _require_all("trigger", triggers, REQUIRED_TRIGGERS)

    function_exists = connection.execute(
        text(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = current_schema() "
            "AND p.proname = 'unicode_casefold')"
        )
    ).scalar_one()
    if not function_exists:
        raise RuntimeError("PostgreSQL thiếu function unicode_casefold(text)")


def _first(connection, sql: str):
    return connection.execute(text(sql)).first()


def _validate_business_invariants(connection) -> None:
    invalid_session = _first(
        connection,
        """
        SELECT id, status
        FROM parking_sessions
        WHERE status = 'checking_out'
           OR status NOT IN ('active', 'completed', 'cancelled')
           OR (status = 'completed' AND (
               check_out_time IS NULL OR parking_fee IS NULL
               OR staff_out_id IS NULL OR check_out_time < check_in_time))
           OR (status = 'active' AND (
               check_out_time IS NOT NULL OR parking_fee IS NOT NULL
               OR staff_out_id IS NOT NULL))
        ORDER BY id LIMIT 1
        """,
    )
    if invalid_session:
        raise RuntimeError(
            "Bất biến vòng đời parking_sessions PostgreSQL không hợp lệ: "
            f"{tuple(invalid_session)}"
        )

    occupancy_drift = _first(
        connection,
        """
        SELECT slot.id, slot.is_occupied,
               EXISTS (
                   SELECT 1 FROM parking_sessions session
                   WHERE session.parking_slot_id = slot.id
                     AND session.status IN ('active', 'checking_out')
               ) AS expected_is_occupied
        FROM parking_slots slot
        WHERE slot.is_occupied IS DISTINCT FROM EXISTS (
            SELECT 1 FROM parking_sessions session
            WHERE session.parking_slot_id = slot.id
              AND session.status IN ('active', 'checking_out')
        )
        ORDER BY slot.id LIMIT 1
        """,
    )
    if occupancy_drift:
        raise RuntimeError(
            "Bất biến parking_slots.is_occupied PostgreSQL không khớp phiên "
            f"active: {tuple(occupancy_drift)}"
        )

    invalid_entitlement = _first(
        connection,
        """
        SELECT session.id, session.vehicle_id, session.monthly_pass_id
        FROM parking_sessions session
        LEFT JOIN monthly_passes pass ON pass.id = session.monthly_pass_id
        WHERE session.monthly_pass_id IS NOT NULL AND (
            pass.id IS NULL OR pass.vehicle_id <> session.vehicle_id
            OR pass.start_date > session.check_in_time::date
            OR pass.end_date < session.check_in_time::date)
        ORDER BY session.id LIMIT 1
        """,
    )
    if invalid_entitlement:
        raise RuntimeError(
            "Bất biến quyền lợi vé tháng PostgreSQL không hợp lệ: "
            f"{tuple(invalid_entitlement)}"
        )

    missing_rate = _first(
        connection,
        """
        SELECT session.id, session.vehicle_id
        FROM parking_sessions session
        JOIN vehicles vehicle ON vehicle.id = session.vehicle_id
        WHERE session.status IN ('active', 'checking_out')
          AND NOT EXISTS (
              SELECT 1 FROM price_configs rate
              WHERE rate.vehicle_type_id = vehicle.vehicle_type_id
                AND rate.is_active
                AND rate.effective_date <= session.check_in_time::date)
        ORDER BY session.id LIMIT 1
        """,
    )
    if missing_rate:
        raise RuntimeError(
            "Phiên PostgreSQL đang mở thiếu bảng giá hiệu lực: "
            f"{tuple(missing_rate)}"
        )

    invalid_slot = _first(
        connection,
        """
        SELECT session.id, session.parking_slot_id
        FROM parking_sessions session
        JOIN vehicles vehicle ON vehicle.id = session.vehicle_id
        LEFT JOIN parking_slots slot ON slot.id = session.parking_slot_id
        LEFT JOIN zones zone ON zone.id = slot.zone_id
        WHERE session.status IN ('active', 'checking_out')
          AND session.parking_slot_id IS NOT NULL
          AND (slot.id IS NULL OR zone.id IS NULL
               OR slot.vehicle_type_id <> vehicle.vehicle_type_id
               OR NOT slot.is_active OR NOT zone.is_active)
        ORDER BY session.id LIMIT 1
        """,
    )
    if invalid_slot:
        raise RuntimeError(
            "Admission slot/zone PostgreSQL không hợp lệ: "
            f"{tuple(invalid_slot)}"
        )


def check_postgres_readiness(engine: Engine, *, deep: bool = True) -> None:
    """Fail closed unless PostgreSQL is migrated and business-consistent.

    Shallow mode is safe for frequent container/proxy probes: connectivity,
    Alembic revision and catalog backstops only. Deployment gates use deep
    mode to scan cross-table business invariants before traffic switches.
    """
    if engine.url.get_backend_name() != "postgresql":
        raise RuntimeError("PostgreSQL readiness received a non-PostgreSQL engine")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
        _validate_catalog(connection)
        if deep:
            _validate_business_invariants(connection)


def assert_postgres_release_revision(engine: Engine) -> None:
    """Deployment-only gate: the database must equal this image's head.

    Application health intentionally does *not* require equality. During an
    expand-contract release, the old blue container must stay healthy after
    the new migration is applied and before green receives traffic.
    """
    if engine.url.get_backend_name() != "postgresql":
        raise RuntimeError("PostgreSQL revision gate received another dialect")
    with engine.connect() as connection:
        actual = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    if actual != POSTGRES_SCHEMA_REVISION:
        raise RuntimeError(
            "PostgreSQL schema revision không khớp image release: "
            f"expected={POSTGRES_SCHEMA_REVISION}, actual={actual}"
        )
