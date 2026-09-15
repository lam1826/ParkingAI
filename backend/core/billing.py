"""Immutable admission tariffs and exact, whole-block billing arithmetic."""
from datetime import datetime, time, timedelta

from fastapi import HTTPException

from core.clock import BUSINESS_TZ
from core.money import MAX_EXACT_VND, ExactVndRangeError, require_exact_vnd

BILLING_POLICY_VERSION = "entry-v1"
PREPAID_POLICY_VERSION = "prepaid-window-v1"
SNAPSHOT_FIELDS = (
    "billing_policy_version", "rate_config_id", "rate_ticket_type",
    "rate_unit_price", "rate_effective_date",
)


def snapshot_values(rate):
    try:
        unit_price = require_exact_vnd(rate.price, label="Đơn giá")
    except ExactVndRangeError as exc:
        raise HTTPException(500, "Dữ liệu bảng giá của lượt gửi không hợp lệ.") from exc
    return dict(zip(SNAPSHOT_FIELDS, (
        BILLING_POLICY_VERSION, rate.id, rate.ticket_type, unit_price, rate.effective_date,
    )))


def billing_basis(*, time_in, time_out, unit_price, ticket_type, rate_id,
                  effective_date, policy_version, coverage_end=None, prepaid_end=None):
    """Round positive microseconds upwards, avoiding float boundary errors."""
    if time_out < time_in:
        raise HTTPException(400, "Thời gian không hợp lệ.")
    start = time_in
    if prepaid_end is not None and policy_version == PREPAID_POLICY_VERSION:
        start = max(start, prepaid_end)
    if coverage_end is not None and policy_version == BILLING_POLICY_VERSION:
        # No representable departure can outlive date.max coverage.
        try:
            end = datetime.combine(coverage_end + timedelta(days=1), time.min)
        except OverflowError:
            end = datetime.max
        if time_in.tzinfo is not None:
            end = end.replace(tzinfo=time_in.tzinfo)
        start = max(start, end)
    elapsed = max(time_out - start, timedelta())
    microseconds = (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds
    seconds = (microseconds + 999_999) // 1_000_000
    if ticket_type not in ("HOURLY", "DAILY") or type(unit_price) is not int or not 0 <= unit_price <= MAX_EXACT_VND:
        raise HTTPException(500, "Dữ liệu bảng giá của lượt gửi không hợp lệ.")
    block_seconds = 3600 if ticket_type == "HOURLY" else 86400
    blocks = (seconds + block_seconds - 1) // block_seconds
    if blocks * unit_price > MAX_EXACT_VND:
        raise HTTPException(422, "Phí gửi xe vượt giới hạn VND chính xác.")
    return {
        "policy_version": policy_version,
        "rate_source": ("prepaid_snapshot" if policy_version == PREPAID_POLICY_VERSION else
                        "entry_snapshot" if policy_version == BILLING_POLICY_VERSION else "legacy_current_rate"),
        "rate_id": rate_id, "unit_price": unit_price, "ticket_type": ticket_type,
        "effective_date": effective_date.isoformat() if effective_date is not None else None,
        "billable_from": start.replace(tzinfo=BUSINESS_TZ) if start.tzinfo is None else start.astimezone(BUSINESS_TZ),
        "billable_seconds": seconds, "billable_blocks": blocks,
    }


def snapshot_basis(session, at):
    if session.billing_policy_version is None:
        return None
    if session.billing_policy_version not in (BILLING_POLICY_VERSION, PREPAID_POLICY_VERSION):
        raise HTTPException(500, "Phiên bản tính phí của lượt gửi không được hỗ trợ.")
    return billing_basis(
        time_in=session.check_in_time, time_out=at,
        unit_price=session.rate_unit_price, ticket_type=session.rate_ticket_type,
        rate_id=session.rate_config_id, effective_date=session.rate_effective_date,
        policy_version=session.billing_policy_version,
        coverage_end=session.monthly_coverage_end if session.monthly_pass_id is not None else None,
        prepaid_end=getattr(session, "prepaid_end_at", None),
    )
