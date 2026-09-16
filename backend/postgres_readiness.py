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


POSTGRES_SCHEMA_REVISION = "20260916_07"

REQUIRED_COLUMN_CONTRACTS = frozenset({
    "parking_sessions.billing_policy_version:character varying:32:YES",
    "parking_sessions.rate_config_id:integer::YES",
    "parking_sessions.rate_ticket_type:character varying:8:YES",
    "parking_sessions.rate_unit_price:bigint::YES",
    "parking_sessions.rate_effective_date:date::YES",
    "site_ai_analyses.site_id:integer::NO",
    "site_ai_analyses.context:json::NO",
    "payments.site_id:integer::YES",
    "cash_shifts.site_id:integer::YES",
    "audit_logs.request_id:character varying:64:YES",
    "audit_logs.site_id:integer::YES",
    "audit_logs.duration_ms:integer::YES",
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
        "site_ai_analyses",
        "audit_logs",
        "parking_cards",
        "cash_shifts",
        "payments",
    }
)

REQUIRED_INDEXES = frozenset(
    {
        "uq_roles_name",
        "ix_site_ai_history",
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
        "uq_site_ai_request",
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
        "trg_parking_sessions_billing_snapshot_guard",
    }
)


# Exception evidence is additive and cannot disappear on application rollback.
REQUIRED_TABLES = REQUIRED_TABLES | frozenset({"parking_session_events"})
REQUIRED_COLUMN_CONTRACTS = REQUIRED_COLUMN_CONTRACTS | frozenset({
    "parking_session_events.id:character varying:36:NO",
    "parking_session_events.session_id:character varying:36:NO",
    "parking_session_events.site_id:integer::YES",
    "parking_session_events.action:character varying:20:NO",
    "parking_session_events.reason:character varying:500:NO",
    "parking_session_events.request_id:character varying:64:NO",
    "parking_session_events.actor_id:integer::NO",
    "parking_session_events.actor_username:character varying:50:NO",
    "parking_session_events.created_at:timestamp without time zone::NO",
    "parking_session_events.before_state:json::NO",
    "parking_session_events.after_state:json::NO",
    "parking_session_events.replacement_session_id:character varying:36:YES",
})
REQUIRED_CONSTRAINTS = REQUIRED_CONSTRAINTS | frozenset({
    "uq_session_event_request", "ck_session_event_action", "ck_session_event_reason",
    "ck_session_event_request", "ck_session_event_actor", "ck_session_event_replacement",
})
REQUIRED_TRIGGERS = REQUIRED_TRIGGERS | frozenset({"trg_session_event_guard", "trg_session_event_session_delete"})
REQUIRED_INDEXES = REQUIRED_INDEXES | frozenset({
    "ix_parking_session_events_session_id", "ix_parking_session_events_site_id",
    "ix_parking_session_events_replacement_session_id",
})

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
REQUIRED_TRIGGERS = REQUIRED_TRIGGERS | frozenset({"trg_zone_commitment_guard"})
REQUIRED_TRIGGERS = REQUIRED_TRIGGERS | frozenset({"trg_payment_demo_boundary"})
REQUIRED_TRIGGERS = REQUIRED_TRIGGERS | frozenset({"trg_payment_site_guard", "trg_cash_shift_site_immutable"})
REQUIRED_INDEXES = REQUIRED_INDEXES | frozenset({"ix_payments_site_id", "ix_cash_shifts_site_id", "ix_audit_logs_request_id", "ix_audit_logs_site_id"})

# Prepaid windows revision 20260915_03.
REQUIRED_TABLES |= frozenset({"parking_capacity_holds", "timed_parking_passes"})
REQUIRED_COLUMN_CONTRACTS -= frozenset({"subscription_plans.duration_days:integer::NO"})
REQUIRED_COLUMN_CONTRACTS |= frozenset(['parking_sites.customer_booking_mode:character varying:16:NO', 'subscription_plans.product_kind:character varying:8:NO', 'subscription_plans.duration_minutes:integer::YES', 'portal_orders.product_kind:character varying:8:NO', 'portal_orders.plan_name:character varying:100:YES', 'portal_orders.duration_days:integer::YES', 'portal_orders.duration_minutes:integer::YES', 'portal_orders.start_at:timestamp without time zone::YES', 'portal_orders.end_at:timestamp without time zone::YES', 'portal_orders.arrival_deadline:timestamp without time zone::YES', 'portal_orders.zone_id:integer::YES', 'portal_orders.slot_id:integer::YES', 'portal_orders.requested_zone_id:integer::YES', 'portal_orders.rate_config_id:integer::YES', 'portal_orders.rate_ticket_type:character varying:8:YES', 'portal_orders.rate_unit_price:bigint::YES', 'portal_orders.rate_effective_date:date::YES', 'portal_orders.timed_pass_id:character varying:36:YES', 'parking_reservations.order_id:character varying:36:YES', 'parking_sessions.timed_pass_id:character varying:36:YES', 'parking_sessions.prepaid_start_at:timestamp without time zone::YES', 'parking_sessions.prepaid_end_at:timestamp without time zone::YES', 'parking_capacity_holds.id:character varying:36:NO', 'parking_capacity_holds.order_id:character varying:36:NO', 'parking_capacity_holds.site_id:integer::NO', 'parking_capacity_holds.slot_id:integer::NO', 'parking_capacity_holds.customer_id:integer::NO', 'parking_capacity_holds.vehicle_id:integer::NO', 'parking_capacity_holds.start_at:timestamp without time zone::NO', 'parking_capacity_holds.end_at:timestamp without time zone::NO', 'parking_capacity_holds.expires_at:timestamp without time zone::NO', 'parking_capacity_holds.status:character varying:12:NO', 'parking_capacity_holds.reservation_id:character varying:36:YES', 'parking_capacity_holds.created_at:timestamp without time zone::NO', 'timed_parking_passes.id:character varying:36:NO', 'timed_parking_passes.order_id:character varying:36:NO', 'timed_parking_passes.reservation_id:character varying:36:NO', 'timed_parking_passes.site_id:integer::NO', 'timed_parking_passes.slot_id:integer::NO', 'timed_parking_passes.customer_id:integer::NO', 'timed_parking_passes.vehicle_id:integer::NO', 'timed_parking_passes.vehicle_type_id:integer::NO', 'timed_parking_passes.start_at:timestamp without time zone::NO', 'timed_parking_passes.end_at:timestamp without time zone::NO', 'timed_parking_passes.arrival_deadline:timestamp without time zone::NO', 'timed_parking_passes.amount:bigint::NO', 'timed_parking_passes.rate_config_id:integer::NO', 'timed_parking_passes.rate_ticket_type:character varying:8:NO', 'timed_parking_passes.rate_unit_price:bigint::NO', 'timed_parking_passes.rate_effective_date:date::NO', 'timed_parking_passes.status:character varying:12:NO', 'timed_parking_passes.session_id:character varying:36:YES', 'timed_parking_passes.created_at:timestamp without time zone::NO', 'subscription_plans.duration_days:integer::YES'])
REQUIRED_TRIGGERS |= frozenset(['trg_site_booking_mode_insert', 'trg_site_booking_mode_update', 'trg_timed_order_insert', 'trg_timed_order_price_source', 'trg_timed_order_immutable', 'trg_timed_order_delete', 'trg_timed_order_replace', 'trg_timed_order_fulfilled', 'trg_capacity_hold_insert', 'trg_capacity_hold_update', 'trg_parking_capacity_holds_delete', 'trg_parking_capacity_holds_replace', 'trg_timed_parking_passes_delete', 'trg_timed_parking_passes_replace', 'trg_timed_pass_insert', 'trg_timed_pass_update', 'trg_parking_reservations_capacity_hold', 'trg_guaranteed_allocations_capacity_hold', 'trg_reservation_order_identity', 'trg_reservation_paid_source', 'trg_parking_reservations_paid_booking_mode', 'trg_site_waitlist_paid_booking_mode', 'trg_session_prepaid_immutable', 'trg_session_prepaid_source', 'trg_session_capacity_hold', 'trg_payment_prepaid_source', 'trg_parking_slots_hold_operational', 'trg_zones_hold_operational', 'trg_vehicle_types_hold_operational', 'trg_parking_sites_hold_operational'])
REQUIRED_INDEXES |= frozenset(['ix_capacity_hold_slot_window', 'ix_capacity_hold_due', 'ix_timed_pass_vehicle', 'ix_timed_pass_customer', 'uq_portal_orders_timed_pass_id', 'uq_parking_sessions_timed_pass_id', 'uq_parking_reservations_order_id'])
REQUIRED_CONSTRAINTS |= frozenset(['ck_capacity_hold_window', 'ck_capacity_hold_status', 'ck_timed_pass_status', 'ck_timed_pass_money', 'ck_timed_pass_window', 'ck_portal_order_product', 'ck_portal_order_timed'])

# Additive online_payments revision 20260915_04.
REQUIRED_TABLES |= frozenset(['online_payment_links',
 'online_payment_inbox',
 'online_payment_processing',
 'online_payment_review_decisions'])
REQUIRED_COLUMN_CONTRACTS |= frozenset(['online_payment_links.id:bigint::NO',
 'online_payment_links.order_id:character varying:36:NO',
 'online_payment_links.site_id:integer::NO',
 'online_payment_links.channel:character varying:64:NO',
 'online_payment_links.receiver_digest:character varying:64:NO',
 'online_payment_links.amount:bigint::NO',
 'online_payment_links.currency:character varying:3:NO',
 'online_payment_links.description:character varying:9:NO',
 'online_payment_links.return_url:character varying:2048:NO',
 'online_payment_links.cancel_url:character varying:2048:NO',
 'online_payment_links.expires_at:timestamp without time zone::NO',
 'online_payment_links.created_at:timestamp without time zone::NO',
 'online_payment_links.state:character varying:12:NO',
 'online_payment_links.provider_status:character varying:12:YES',
 'online_payment_links.payment_link_id:character varying:64:YES',
 'online_payment_links.checkout_url:character varying:2048:YES',
 'online_payment_links.qr_code:text::YES',
 'online_payment_links.settled_reference:character varying:64:YES',
 'online_payment_links.receipt_id:character varying:36:YES',
 'online_payment_links.review_reason:character varying:100:YES',
 'online_payment_links.last_error:character varying:100:YES',
 'online_payment_links.operation_token:character varying:36:YES',
 'online_payment_links.operation_until:timestamp without time zone::YES',
 'online_payment_links.last_checked_at:timestamp without time zone::YES',
 'online_payment_inbox.id:character varying:36:NO',
 'online_payment_inbox.link_id:bigint::YES',
 'online_payment_inbox.site_id:integer::NO',
 'online_payment_inbox.channel:character varying:64:NO',
 'online_payment_inbox.source:character varying:12:NO',
 'online_payment_inbox.order_code:bigint::NO',
 'online_payment_inbox.payment_link_id:character varying:64:NO',
 'online_payment_inbox.reference:character varying:64:NO',
 'online_payment_inbox.amount:bigint::NO',
 'online_payment_inbox.currency:character varying:3:NO',
 'online_payment_inbox.receiver_digest:character varying:64:NO',
 'online_payment_inbox.transaction_time:character varying:64:NO',
 'online_payment_inbox.payload_digest:character varying:64:NO',
 'online_payment_inbox.received_at:timestamp without time zone::NO',
 'online_payment_inbox.verification_issue:character varying:100:YES',
 'online_payment_processing.id:character varying:36:NO',
 'online_payment_processing.status:character varying:12:NO',
 'online_payment_processing.reason:character varying:100:YES',
 'online_payment_processing.attempts:integer::NO',
 'online_payment_processing.next_attempt_at:timestamp without time zone::YES',
 'online_payment_processing.receipt_id:character varying:36:YES',
 'online_payment_processing.processed_at:timestamp without time zone::YES',
 'online_payment_review_decisions.id:character varying:36:NO',
 'online_payment_review_decisions.inbox_id:character varying:36:NO',
 'online_payment_review_decisions.channel:character varying:64:NO',
 'online_payment_review_decisions.payment_reference:character varying:64:NO',
 'online_payment_review_decisions.action:character varying:32:NO',
 'online_payment_review_decisions.request_id:character varying:64:NO',
 'online_payment_review_decisions.reason:character varying:500:NO',
 'online_payment_review_decisions.actor_id:integer::NO',
 'online_payment_review_decisions.actor_username:character varying:50:NO',
 'online_payment_review_decisions.refund_amount:bigint::YES',
 'online_payment_review_decisions.external_reference:character varying:120:YES',
 'online_payment_review_decisions.created_at:timestamp without time zone::NO'])
REQUIRED_INDEXES |= frozenset(['ix_online_payment_links_channel',
 'ix_online_payment_links_site_id',
 'ix_online_payment_inbox_channel',
 'ix_online_payment_inbox_link_id',
 'ix_online_payment_inbox_reference',
 'ix_online_payment_inbox_site_id',
 'ix_online_payment_processing_next_attempt_at',
 'ix_online_payment_processing_status',
 'ix_online_payment_review_decisions_inbox_id',
 'uq_online_review_final_reference'])
REQUIRED_CONSTRAINTS |= frozenset(['ck_online_link_amount',
 'ck_online_link_code',
 'ck_online_link_state',
 'ck_online_inbox_amount',
 'ck_online_inbox_code',
 'ck_online_inbox_source',
 'uq_online_inbox_evidence',
 'ck_online_processing_attempts',
 'ck_online_processing_receipt',
 'ck_online_processing_status',
 'ck_online_processing_time',
 'ck_online_review_action',
 'ck_online_review_reason',
 'ck_online_review_refund',
 'uq_online_review_request'])
REQUIRED_TRIGGERS |= frozenset(['trg_online_link_guard',
 'trg_online_inbox_guard',
 'trg_online_processing_guard',
 'trg_online_order_delete',
 'trg_online_review_guard'])

# Additive occupancy_observations revision 20260915_05.
REQUIRED_TABLES |= frozenset(['occupancy_calibrations', 'occupancy_calibration_slots', 'occupancy_observations'])
REQUIRED_COLUMN_CONTRACTS |= frozenset(['occupancy_calibrations.id:character varying:36:NO',
 'occupancy_calibrations.site_id:integer::NO',
 'occupancy_calibrations.camera_id:integer::NO',
 'occupancy_calibrations.version:integer::NO',
 'occupancy_calibrations.reference_observation_id:character varying:36:YES',
 'occupancy_calibrations.reference_id_snapshot:character varying:36:NO',
 'occupancy_calibrations.reference_image_hash:character varying:64:NO',
 'occupancy_calibrations.reference_width:integer::NO',
 'occupancy_calibrations.reference_height:integer::NO',
 'occupancy_calibrations.reference_observed_at:timestamp without time zone::NO',
 'occupancy_calibrations.reference_expires_at:timestamp without time zone::NO',
 'occupancy_calibrations.engine:character varying:40:NO',
 'occupancy_calibrations.settings_schema_version:integer::NO',
 'occupancy_calibrations.regions:json::NO',
 'occupancy_calibrations.settings:json::NO',
 'occupancy_calibrations.request_id:character varying:64:NO',
 'occupancy_calibrations.payload_hash:character varying:64:NO',
 'occupancy_calibrations.created_by_id:integer::NO',
 'occupancy_calibrations.created_at:timestamp without time zone::NO',
 'occupancy_calibration_slots.calibration_id:character varying:36:NO',
 'occupancy_calibration_slots.slot_id:integer::NO',
 'occupancy_observations.id:character varying:36:NO',
 'occupancy_observations.calibration_id:character varying:36:NO',
 'occupancy_observations.source_observation_id:character varying:36:YES',
 'occupancy_observations.source_id_snapshot:character varying:36:NO',
 'occupancy_observations.source_image_hash:character varying:64:NO',
 'occupancy_observations.measured_at:timestamp without time zone::NO',
 'occupancy_observations.received_at:timestamp without time zone::NO',
 'occupancy_observations.expires_at:timestamp without time zone::NO',
 'occupancy_observations.analyzed_at:timestamp without time zone::NO',
 'occupancy_observations.analyzed_by_id:integer::NO',
 'occupancy_observations.engine:character varying:40:NO',
 'occupancy_observations.quality:json::NO',
 'occupancy_observations.readings:json::NO'])
REQUIRED_INDEXES |= frozenset(['ix_occupancy_calibrations_camera_id',
 'ix_occupancy_calibrations_site_id',
 'ix_occupancy_calibration_slots_slot_id',
 'ix_occupancy_observations_calibration_id',
 'ix_occupancy_observations_measured_at'])
REQUIRED_CONSTRAINTS |= frozenset(['ck_occupancy_calibration_engine',
 'ck_occupancy_calibration_version',
 'ck_occupancy_settings_version',
 'uq_occupancy_calibration_request',
 'uq_occupancy_camera_version',
 'ck_occupancy_observation_engine',
 'uq_occupancy_calibration_source'])



# Additive session credits revision 20260915_06.
REQUIRED_COLUMN_CONTRACTS -= frozenset({"online_payment_links.order_id:character varying:36:NO"})
REQUIRED_TABLES |= frozenset(['session_fee_quotes', 'session_fee_credits'])
REQUIRED_COLUMN_CONTRACTS |= frozenset(['session_fee_quotes.id:character varying:36:NO',
 'session_fee_quotes.session_id:character varying:36:NO',
 'session_fee_quotes.site_id:integer::NO',
 'session_fee_quotes.created_by_id:integer::NO',
 'session_fee_quotes.owner_customer_id:integer::YES',
 'session_fee_quotes.request_id:character varying:64:NO',
 'session_fee_quotes.session_state_hash:character varying:64:NO',
 'session_fee_quotes.credit_snapshot_hash:character varying:64:NO',
 'session_fee_quotes.gross_fee:bigint::NO',
 'session_fee_quotes.credited_amount:bigint::NO',
 'session_fee_quotes.amount:bigint::NO',
 'session_fee_quotes.quoted_at:timestamp without time zone::NO',
 'session_fee_quotes.paid_through:timestamp without time zone::NO',
 'session_fee_quotes.expires_at:timestamp without time zone::NO',
 'session_fee_quotes.billing_basis:json::NO',
 'session_fee_quotes.status:character varying:12:NO',
 'session_fee_quotes.review_reason:character varying:100:YES',
 'session_fee_quotes.credit_id:character varying:36:YES',
 'session_fee_quotes.receipt_id:character varying:36:YES',
 'session_fee_credits.id:character varying:36:NO',
 'session_fee_credits.session_id:character varying:36:NO',
 'session_fee_credits.quote_id:character varying:36:NO',
 'session_fee_credits.amount:bigint::NO',
 'session_fee_credits.paid_through:timestamp without time zone::NO',
 'session_fee_credits.created_at:timestamp without time zone::NO',
 'session_fee_credits.receipt_id:character varying:36:YES',
 'online_payment_links.order_id:character varying:36:YES',
 'online_payment_links.session_quote_id:character varying:36:YES'])
REQUIRED_INDEXES |= frozenset(['ix_session_fee_quotes_session_id',
 'ix_session_fee_quotes_site_id',
 'uq_session_fee_pending',
 'ix_session_fee_credits_session_id',
 'uq_online_payment_links_session_quote_id'])
REQUIRED_CONSTRAINTS |= frozenset(['ck_session_fee_quote_fulfilled',
 'ck_session_fee_quote_money',
 'ck_session_fee_quote_status',
 'ck_session_fee_quote_time',
 'uq_session_fee_quote_request',
 'ck_session_fee_credit_money',
 'ck_online_link_target'])
REQUIRED_TRIGGERS |= frozenset(['trg_session_fee_quote_guard',
 'trg_session_fee_credit_guard',
 'trg_session_fee_payment_source',
 'trg_session_fee_session_guard'])


# Additive public lot profile, customer support and receipt refunds, revision 20260916_07.
REQUIRED_TABLES |= frozenset(['customer_support_requests', 'customer_support_messages', 'payment_refund_requests'])
REQUIRED_COLUMN_CONTRACTS |= frozenset(['parking_sites.public_description:character varying:2000:YES',
 'parking_sites.public_opening_hours:character varying:500:YES',
 'parking_sites.public_contact_phone:character varying:20:YES',
 'parking_sites.public_contact_email:character varying:100:YES',
 'parking_sites.latitude:double precision::YES',
 'parking_sites.longitude:double precision::YES',
 'parking_sites.public_profile_updated_at:timestamp without time zone::YES',
 'parking_sites.public_profile_updated_by_id:integer::YES',
 'customer_support_requests.id:character varying:36:NO',
 'customer_support_requests.site_id:integer::NO',
 'customer_support_requests.customer_id:integer::NO',
 'customer_support_requests.user_id:integer::NO',
 'customer_support_requests.subject:character varying:150:NO',
 'customer_support_requests.category:character varying:16:NO',
 'customer_support_requests.status:character varying:12:NO',
 'customer_support_requests.linked_type:character varying:16:YES',
 'customer_support_requests.linked_id:character varying:36:YES',
 'customer_support_requests.created_at:timestamp without time zone::NO',
 'customer_support_requests.updated_at:timestamp without time zone::NO',
 'customer_support_requests.last_message_at:timestamp without time zone::NO',
 'customer_support_requests.closed_at:timestamp without time zone::YES',
 'customer_support_requests.closed_by_id:integer::YES',
 'customer_support_messages.id:character varying:36:NO',
 'customer_support_messages.request_id:character varying:36:NO',
 'customer_support_messages.author_id:integer::NO',
 'customer_support_messages.author_role:character varying:12:NO',
 'customer_support_messages.body:character varying:2000:NO',
 'customer_support_messages.created_at:timestamp without time zone::NO',
 'payment_refund_requests.id:character varying:36:NO',
 'payment_refund_requests.receipt_id:character varying:36:NO',
 'payment_refund_requests.site_id:integer::YES',
 'payment_refund_requests.customer_id:integer::NO',
 'payment_refund_requests.user_id:integer::NO',
 'payment_refund_requests.source_type:character varying:24:NO',
 'payment_refund_requests.source_id:character varying:36:NO',
 'payment_refund_requests.payment_channel:character varying:8:NO',
 'payment_refund_requests.receipt_method:character varying:16:NO',
 'payment_refund_requests.reason:character varying:500:NO',
 'payment_refund_requests.requested_amount:bigint::NO',
 'payment_refund_requests.status:character varying:12:NO',
 'payment_refund_requests.approved_amount:bigint::YES',
 'payment_refund_requests.decision_note:character varying:500:NO',
 'payment_refund_requests.reviewed_by_id:integer::YES',
 'payment_refund_requests.reviewed_at:timestamp without time zone::YES',
 'payment_refund_requests.refund_payment_id:character varying:36:YES',
 'payment_refund_requests.refund_method:character varying:16:YES',
 'payment_refund_requests.external_reference:character varying:120:YES',
 'payment_refund_requests.refunded_by_id:integer::YES',
 'payment_refund_requests.refunded_at:timestamp without time zone::YES',
 'payment_refund_requests.created_at:timestamp without time zone::NO',
 'payment_refund_requests.updated_at:timestamp without time zone::NO'])
REQUIRED_INDEXES |= frozenset(['ix_customer_support_requests_customer_id',
 'ix_support_request_site_status',
 'ix_customer_support_messages_request_id',
 'ix_payment_refund_requests_customer_id',
 'ix_payment_refund_requests_receipt_id',
 'ix_refund_request_site_status',
 'uq_payment_refund_open'])
REQUIRED_CONSTRAINTS |= frozenset(['ck_support_request_category',
 'ck_support_request_status',
 'ck_support_request_link',
 'ck_support_request_subject',
 'ck_support_request_closed',
 'ck_support_message_role',
 'ck_support_message_body',
 'ck_refund_request_status',
 'ck_refund_request_channel',
 'ck_refund_request_amount',
 'ck_refund_request_approved',
 'ck_refund_request_approved_amount',
 'ck_refund_request_reviewed',
 'ck_refund_request_refunded'])

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
               OR parking_fee < COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE c.session_id=parking_sessions.id AND c.receipt_id IS NOT NULL),0)
               OR (parking_fee = COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE c.session_id=parking_sessions.id AND c.receipt_id IS NOT NULL),0) AND checkout_payment_method IS NOT NULL)
               OR (parking_fee > COALESCE((SELECT SUM(c.amount) FROM session_fee_credits c WHERE c.session_id=parking_sessions.id AND c.receipt_id IS NOT NULL),0) AND COALESCE(checkout_payment_method, '') NOT IN ('cash', 'transfer'))))
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
          AND session.billing_policy_version IS NULL
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
