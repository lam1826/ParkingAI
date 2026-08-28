from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.client_ip import get_client_ip
from core.config import settings
from models.audit_log import AuditLog


def _recent_attempt_count(
    db: Session,
    *,
    action: str,
    ip_address: str | None,
    window_seconds: int,
    failures_only: bool,
) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=window_seconds
    )
    query = select(func.count(AuditLog.id)).where(
        AuditLog.action == action,
        AuditLog.ip_address == ip_address,
        AuditLog.created_at >= cutoff,
    )
    if failures_only:
        query = query.where(AuditLog.success.is_(False))
    return db.execute(query).scalar_one()


def enforce_login_rate_limit(request: Request, db: Session) -> None:
    failures = _recent_attempt_count(
        db,
        action="LOGIN",
        ip_address=get_client_ip(request),
        window_seconds=settings.AUTH_LOGIN_WINDOW_SECONDS,
        failures_only=True,
    )
    if failures >= settings.AUTH_LOGIN_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau.",
            headers={"Retry-After": str(settings.AUTH_LOGIN_WINDOW_SECONDS)},
        )


def enforce_registration_rate_limit(request: Request, db: Session) -> None:
    attempts = _recent_attempt_count(
        db,
        action="REGISTER",
        ip_address=get_client_ip(request),
        window_seconds=settings.AUTH_REGISTER_WINDOW_SECONDS,
        failures_only=False,
    )
    if attempts >= settings.AUTH_REGISTER_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quá nhiều lần đăng ký. Vui lòng thử lại sau.",
            headers={"Retry-After": str(settings.AUTH_REGISTER_WINDOW_SECONDS)},
        )
