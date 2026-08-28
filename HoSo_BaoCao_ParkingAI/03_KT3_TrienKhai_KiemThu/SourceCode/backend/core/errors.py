"""Stable public errors while retaining diagnostic detail in server logs."""

import logging

from fastapi import HTTPException, status


DATABASE_BUSINESS_CONFLICT_MARKERS = (
    "vehicle type immutable after history",
    "license plate immutable after history",
    "monthly pass history immutable",
    "active parking session uses price config",
    "zone capacity below slot count",
    "zone has active parking",
    "zone capacity exceeded",
    "slot zone immutable after history",
    "slot has active parking",
    "monthly pass is not eligible at check-in",
    "active parking session requires effective price config",
    "parking slot is not eligible for active session",
    "parking session identity is immutable",
    "completed parking session is immutable",
    "parking session status invalid",
)


def is_known_database_business_conflict(error: Exception) -> bool:
    """Recognize fail-closed DB backstops without exposing raw SQL details."""
    original = getattr(error, "orig", None)
    message = str(original if original is not None else error).lower()
    return any(marker in message for marker in DATABASE_BUSINESS_CONFLICT_MARKERS)


def internal_server_error(
    logger: logging.Logger,
    *,
    event: str,
    public_detail: str,
    error: Exception,
) -> HTTPException:
    logger.error(
        "%s",
        event,
        exc_info=(type(error), error, error.__traceback__),
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=public_detail,
    )
