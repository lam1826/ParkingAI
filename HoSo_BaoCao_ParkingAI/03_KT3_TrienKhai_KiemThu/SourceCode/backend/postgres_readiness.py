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
from finance_rollout import validate_finance_invariants
from expansion_demo_guards import validate_demo_ledger
from expansion_rollout import validate_zone_site_assignment


POSTGRES_SCHEMA_REVISION = "20260907_02"

REQUIRED_COLUMN_CONTRACTS = frozenset({
    "parking_sessions.checkout_quote_hash:character varying:64:YES",
    "parking_sessions.checkout_payment_method:character varying:8:YES",
})

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
        "parking_cards",
        "cash_shifts",
        "payments",
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
        "uq_monthly_passes_renewal_key",
        "uq_payment_source_receipt",
        "uq_cash_shift_one_open_per_staff",
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
        "ck_parking_sessions_monthly_coverage",
        "fk_monthly_passes_card",
        "ck_shift_opening_cash",
        "ck_shift_counted_cash",
        "ck_shift_expected_cash",
        "ck_shift_difference",
        "ck_shift_state",
        "ck_payment_amount",
        "ck_payment_source",
        "ck_payment_kind",
        "ck_payment_method",
        "ck_payment_legacy_unassigned",
        "ck_payment_refund_reference",
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
        "trg_payment_guard",
        "trg_cash_shift_guard",
        "trg_monthly_finance_guard",
        "trg_parking_card_identity_guard",
        "trg_paid_parking_session_delete",
        "trg_monthly_coverage_guard",
        "trg_parking_sessions_checkout_confirmation_guard",
    }
)


# Expansion revision 20260907_02; explicit catalog contracts stay read-only.
REQUIRED_TABLES = REQUIRED_TABLES | frozenset(['fleet_vehicles',
 'guaranteed_allocations',
 'organization_memberships',
 'organizations',
 'parking_reservations',
 'parking_sites',
 'portal_account_links',
 'portal_link_requests',
 'portal_notifications',
 'portal_orders',
 'portal_payment_events',
 'portal_refund_requests',
 'portal_session_grants',
 'portal_vehicle_ownerships',
 'portal_vehicle_requests',
 'site_memberships',
 'site_waitlist',
 'subscription_plans',
 'vision_cameras',
 'vision_observations'])
REQUIRED_COLUMN_CONTRACTS = REQUIRED_COLUMN_CONTRACTS | frozenset(['fleet_vehicles.created_at:timestamp without time zone::NO',
 'fleet_vehicles.id:integer::NO',
 'fleet_vehicles.organization_id:integer::NO',
 'fleet_vehicles.vehicle_id:integer::NO',
 'guaranteed_allocations.created_at:timestamp without time zone::NO',
 'guaranteed_allocations.created_by_id:integer::NO',
 'guaranteed_allocations.customer_id:integer::NO',
 'guaranteed_allocations.end_at:timestamp without time zone::NO',
 'guaranteed_allocations.id:character varying:36:NO',
 'guaranteed_allocations.request_id:character varying:64:NO',
 'guaranteed_allocations.site_id:integer::NO',
 'guaranteed_allocations.slot_id:integer::NO',
 'guaranteed_allocations.start_at:timestamp without time zone::NO',
 'guaranteed_allocations.status:character varying:12:NO',
 'guaranteed_allocations.vehicle_id:integer::NO',
 'organization_memberships.id:integer::NO',
 'organization_memberships.organization_id:integer::NO',
 'organization_memberships.user_id:integer::NO',
 'organizations.created_at:timestamp without time zone::NO',
 'organizations.id:integer::NO',
 'organizations.is_active:boolean::NO',
 'organizations.name:character varying:150:NO',
 'organizations.site_id:integer::NO',
 'parking_reservations.arrival_deadline:timestamp without time zone::NO',
 'parking_reservations.created_at:timestamp without time zone::NO',
 'parking_reservations.created_by_id:integer::NO',
 'parking_reservations.customer_id:integer::NO',
 'parking_reservations.end_at:timestamp without time zone::NO',
 'parking_reservations.id:character varying:36:NO',
 'parking_reservations.request_id:character varying:64:NO',
 'parking_reservations.session_id:character varying:36:YES',
 'parking_reservations.site_id:integer::NO',
 'parking_reservations.slot_id:integer::NO',
 'parking_reservations.start_at:timestamp without time zone::NO',
 'parking_reservations.status:character varying:12:NO',
 'parking_reservations.vehicle_id:integer::NO',
 'parking_sites.address:character varying:250:NO',
 'parking_sites.created_at:timestamp without time zone::NO',
 'parking_sites.id:integer::NO',
 'parking_sites.is_active:boolean::NO',
 'parking_sites.name:character varying:100:NO',
 'portal_account_links.created_at:timestamp without time zone::NO',
 'portal_account_links.customer_id:integer::NO',
 'portal_account_links.id:integer::NO',
 'portal_account_links.user_id:integer::NO',
 'portal_account_links.verification:character varying:24:NO',
 'portal_account_links.verified_by_id:integer::YES',
 'portal_link_requests.created_at:timestamp without time zone::NO',
 'portal_link_requests.id:character varying:36:NO',
 'portal_link_requests.note:character varying:500:NO',
 'portal_link_requests.phone_number:character varying:20:NO',
 'portal_link_requests.reviewed_by_id:integer::YES',
 'portal_link_requests.status:character varying:12:NO',
 'portal_link_requests.user_id:integer::NO',
 'portal_notifications.created_at:timestamp without time zone::NO',
 'portal_notifications.customer_id:integer::NO',
 'portal_notifications.event_key:character varying:128:NO',
 'portal_notifications.id:character varying:36:NO',
 'portal_notifications.message:character varying:500:NO',
 'portal_notifications.read_at:timestamp without time zone::YES',
 'portal_orders.amount:bigint::NO',
 'portal_orders.card_id:integer::YES',
 'portal_orders.created_at:timestamp without time zone::NO',
 'portal_orders.customer_id:integer::NO',
 'portal_orders.demo_token:character varying:64:YES',
 'portal_orders.end_date:date::NO',
 'portal_orders.expires_at:timestamp without time zone::NO',
 'portal_orders.id:character varying:36:NO',
 'portal_orders.idempotency_key:character varying:64:NO',
 'portal_orders.monthly_pass_id:integer::YES',
 'portal_orders.payment_mode:character varying:8:NO',
 'portal_orders.plan_id:integer::NO',
 'portal_orders.receipt_id:character varying:36:YES',
 'portal_orders.review_reason:character varying:100:YES',
 'portal_orders.site_id:integer::NO',
 'portal_orders.start_date:date::NO',
 'portal_orders.status:character varying:12:NO',
 'portal_orders.user_id:integer::NO',
 'portal_orders.vehicle_id:integer::NO',
 'portal_payment_events.amount:bigint::NO',
 'portal_payment_events.attempts:integer::NO',
 'portal_payment_events.error_code:character varying:100:YES',
 'portal_payment_events.id:character varying:36:NO',
 'portal_payment_events.next_attempt_at:timestamp without time zone::YES',
 'portal_payment_events.order_id:character varying:36:NO',
 'portal_payment_events.outcome:character varying:12:NO',
 'portal_payment_events.provider:character varying:12:NO',
 'portal_payment_events.received_at:timestamp without time zone::NO',
 'portal_payment_events.reference:character varying:64:NO',
 'portal_payment_events.status:character varying:12:NO',
 'portal_refund_requests.created_at:timestamp without time zone::NO',
 'portal_refund_requests.customer_id:integer::NO',
 'portal_refund_requests.id:character varying:36:NO',
 'portal_refund_requests.note:character varying:500:NO',
 'portal_refund_requests.order_id:character varying:36:NO',
 'portal_refund_requests.reason:character varying:500:NO',
 'portal_refund_requests.refund_payment_id:character varying:36:YES',
 'portal_refund_requests.reviewed_by_id:integer::YES',
 'portal_refund_requests.status:character varying:12:NO',
 'portal_session_grants.customer_id:integer::NO',
 'portal_session_grants.parking_session_id:character varying:36:NO',
 'portal_vehicle_ownerships.approved_at:timestamp without time zone::NO',
 'portal_vehicle_ownerships.approved_by_id:integer::NO',
 'portal_vehicle_ownerships.customer_id:integer::NO',
 'portal_vehicle_ownerships.id:integer::NO',
 'portal_vehicle_ownerships.vehicle_id:integer::NO',
 'portal_vehicle_requests.created_at:timestamp without time zone::NO',
 'portal_vehicle_requests.customer_id:integer::NO',
 'portal_vehicle_requests.id:character varying:36:NO',
 'portal_vehicle_requests.license_plate:character varying:20:NO',
 'portal_vehicle_requests.note:character varying:500:NO',
 'portal_vehicle_requests.reviewed_by_id:integer::YES',
 'portal_vehicle_requests.status:character varying:12:NO',
 'portal_vehicle_requests.vehicle_type_id:integer::NO',
 'site_memberships.id:integer::NO',
 'site_memberships.role:character varying:12:NO',
 'site_memberships.site_id:integer::NO',
 'site_memberships.user_id:integer::NO',
 'site_waitlist.created_at:timestamp without time zone::NO',
 'site_waitlist.created_by_id:integer::NO',
 'site_waitlist.customer_id:integer::NO',
 'site_waitlist.end_at:timestamp without time zone::NO',
 'site_waitlist.id:character varying:36:NO',
 'site_waitlist.request_id:character varying:64:NO',
 'site_waitlist.reservation_id:character varying:36:YES',
 'site_waitlist.site_id:integer::NO',
 'site_waitlist.start_at:timestamp without time zone::NO',
 'site_waitlist.status:character varying:12:NO',
 'site_waitlist.vehicle_id:integer::NO',
 'subscription_plans.duration_days:integer::NO',
 'subscription_plans.id:integer::NO',
 'subscription_plans.is_active:boolean::NO',
 'subscription_plans.name:character varying:100:NO',
 'subscription_plans.price:bigint::NO',
 'subscription_plans.site_id:integer::YES',
 'subscription_plans.vehicle_type_id:integer::NO',
 'vision_cameras.created_at:timestamp without time zone::NO',
 'vision_cameras.direction:character varying:8:NO',
 'vision_cameras.edge_token_hash:character varying:64:YES',
 'vision_cameras.id:integer::NO',
 'vision_cameras.is_active:boolean::NO',
 'vision_cameras.name:character varying:100:NO',
 'vision_cameras.retention_hours:integer::NO',
 'vision_cameras.site_id:integer::NO',
 'vision_cameras.zone_id:integer::YES',
 'vision_observations.camera_id:integer::NO',
 'vision_observations.captured_at:timestamp without time zone::NO',
 'vision_observations.confidence:double precision::YES',
 'vision_observations.confirmed_plate:character varying:20:YES',
 'vision_observations.detections:json::NO',
 'vision_observations.engine:character varying:50:NO',
 'vision_observations.event_id:character varying:36:NO',
 'vision_observations.expires_at:timestamp without time zone::NO',
 'vision_observations.id:character varying:36:NO',
 'vision_observations.image_bytes:bytea::NO',
 'vision_observations.image_hash:character varying:64:NO',
 'vision_observations.image_height:integer::NO',
 'vision_observations.image_width:integer::NO',
 'vision_observations.observed_at:timestamp without time zone::NO',
 'vision_observations.ocr_status:character varying:20:NO',
 'vision_observations.review_status:character varying:10:NO',
 'vision_observations.reviewed_at:timestamp without time zone::YES',
 'vision_observations.reviewed_by_id:integer::YES',
 'vision_observations.site_id:integer::NO',
 'vision_observations.suggested_plate:character varying:20:YES',
 'zones.site_id:integer::YES'])
REQUIRED_INDEXES = REQUIRED_INDEXES | frozenset(['ix_allocation_slot_interval',
 'ix_fleet_vehicles_organization_id',
 'ix_guaranteed_allocations_site_id',
 'ix_organization_memberships_organization_id',
 'ix_organizations_site_id',
 'ix_parking_reservations_customer_id',
 'ix_parking_reservations_site_id',
 'ix_parking_reservations_vehicle_id',
 'ix_portal_link_requests_user_id',
 'ix_portal_notifications_customer_id',
 'ix_portal_order_due',
 'ix_portal_orders_customer_id',
 'ix_portal_orders_site_id',
 'ix_portal_orders_user_id',
 'ix_portal_orders_vehicle_id',
 'ix_portal_payment_events_order_id',
 'ix_portal_refund_requests_customer_id',
 'ix_portal_session_grants_customer_id',
 'ix_portal_vehicle_ownerships_customer_id',
 'ix_portal_vehicle_ownerships_vehicle_id',
 'ix_portal_vehicle_requests_customer_id',
 'ix_reservation_slot_interval',
 'ix_site_memberships_site_id',
 'ix_site_memberships_user_id',
 'ix_site_waitlist_site_id',
 'ix_subscription_plans_site_id',
 'ix_vision_cameras_site_id',
 'ix_vision_observations_camera_id',
 'ix_vision_observations_expires_at',
 'ix_vision_observations_site_id',
 'ix_zones_site_id'])
REQUIRED_CONSTRAINTS = REQUIRED_CONSTRAINTS | frozenset(['ck_allocation_interval',
 'ck_allocation_status',
 'ck_camera_direction',
 'ck_camera_retention',
 'ck_payment_demo_unassigned',
 'ck_portal_event_outcome',
 'ck_portal_event_state',
 'ck_portal_link_state',
 'ck_portal_order_amount',
 'ck_portal_order_dates',
 'ck_portal_order_fulfilled',
 'ck_portal_order_mode',
 'ck_portal_order_state',
 'ck_portal_plan_duration',
 'ck_portal_plan_price',
 'ck_portal_refund_state',
 'ck_portal_vehicle_request_state',
 'ck_reservation_arrival',
 'ck_reservation_interval',
 'ck_reservation_status',
 'ck_site_member_role',
 'ck_vision_review_status',
 'ck_waitlist_interval',
 'ck_waitlist_status',
 'fk_zones_site',
 'uq_camera_site_name',
 'uq_fleet_vehicle',
 'uq_organization_member',
 'uq_portal_order_request',
 'uq_portal_provider_reference',
 'uq_portal_vehicle_owner',
 'uq_site_member',
 'uq_vision_camera_event'])
REQUIRED_TRIGGERS = REQUIRED_TRIGGERS | frozenset(['trg_parking_reservations_guard',
 'trg_guaranteed_allocations_guard',
 'trg_slot_commitment_guard',
 'trg_zone_site_immutable'])
REQUIRED_TRIGGERS = REQUIRED_TRIGGERS | frozenset({"trg_payment_demo_boundary"})


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

    column_contracts = connection.execute(text(
        "SELECT table_name || '.' || column_name || ':' || data_type || ':' || "
        "COALESCE(character_maximum_length::text, '') || ':' || is_nullable "
        "FROM information_schema.columns WHERE table_schema = current_schema()"
    )).scalars()
    _require_all("column contract", column_contracts, REQUIRED_COLUMN_CONTRACTS)

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
    validate_zone_site_assignment(connection)
    validate_finance_invariants(connection)
    validate_demo_ledger(connection)
    invalid_confirmation = _first(connection, """
        SELECT id FROM parking_sessions
        WHERE (checkout_quote_hash IS NULL AND checkout_payment_method IS NOT NULL)
           OR (checkout_quote_hash IS NOT NULL AND (
               length(checkout_quote_hash) != 64 OR checkout_quote_hash !~ '^[0-9a-f]{64}$'
               OR status IS DISTINCT FROM 'completed' OR staff_out_id IS NULL
               OR parking_fee IS NULL OR parking_fee < 0
               OR (parking_fee = 0 AND checkout_payment_method IS NOT NULL)
               OR (parking_fee > 0 AND COALESCE(checkout_payment_method, '') NOT IN ('cash', 'transfer'))))
        ORDER BY id LIMIT 1
    """)
    if invalid_confirmation:
        raise RuntimeError(
            "Bất biến checkout confirmation PostgreSQL không hợp lệ: "
            f"{tuple(invalid_confirmation)}"
        )
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
