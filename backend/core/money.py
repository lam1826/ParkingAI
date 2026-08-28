"""Shared bounds for integer VND values.

SQLite legacy FLOAT columns cannot exactly represent integers above 2**53 - 1.
Keeping every API and database backstop within this range prevents silent
rounding while old databases are being rolled forward.
"""

from sqlalchemy import BigInteger, Integer

MAX_EXACT_VND = 9_007_199_254_740_991

# SQLite ``INTEGER`` is signed 64-bit while PostgreSQL ``INTEGER`` is only
# signed 32-bit.  Keep the existing SQLite schema byte-compatible and use
# BIGINT on PostgreSQL so both adapters can honour the public exact-VND range.
VND_DATABASE_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class ExactVndRangeError(RuntimeError):
    """Raised when a monetary value cannot cross JSON/JavaScript exactly."""


def require_exact_vnd(value, *, label: str = "Giá trị VND") -> int:
    """Return an exact non-negative integer or fail closed.

    Individual fees are protected by API validation and SQLite triggers, but
    an aggregate can still exceed ``MAX_EXACT_VND`` even when every row is
    valid. Returning that total as a JSON number would silently change it in a
    JavaScript client, so aggregate/read paths must call this gate as well.
    """
    if isinstance(value, bool):
        raise ExactVndRangeError(
            f"{label} không phải số nguyên VND không âm hợp lệ."
        )
    try:
        exact_value = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExactVndRangeError(
            f"{label} không phải số nguyên VND không âm hợp lệ."
        ) from exc
    if exact_value < 0 or exact_value > MAX_EXACT_VND or exact_value != value:
        if exact_value > MAX_EXACT_VND:
            raise ExactVndRangeError(
                f"{label} vượt phạm vi VND chính xác được hỗ trợ."
            )
        raise ExactVndRangeError(
            f"{label} không phải số nguyên VND không âm hợp lệ."
        )
    return exact_value


def sum_exact_vnd(values, *, label: str = "Tổng doanh thu") -> int:
    """Sum persisted VND values with Python's unbounded integer arithmetic.

    SQLite's integer ``SUM`` raises ``OperationalError: integer overflow`` as
    soon as a valid collection grows beyond signed 64-bit range.  That leaks a
    database implementation detail before :func:`require_exact_vnd` can apply
    the public exact-money contract.  Validate each non-NULL value, add it in
    Python, and validate the aggregate once at the domain boundary instead.

    ``NULL`` is skipped to preserve SQL ``SUM`` semantics for legacy rows.
    Completed-session integrity guards normally ensure fees are non-NULL.
    """
    total = 0
    for value in values:
        if value is None:
            continue
        total += require_exact_vnd(value, label=label)
    return require_exact_vnd(total, label=label)
