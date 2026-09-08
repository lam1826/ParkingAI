import re
import logging
from time import monotonic
from collections.abc import Generator

import jwt
from jwt.exceptions import InvalidTokenError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.concurrency import run_in_threadpool

from core.config import settings
from core.client_ip import get_client_ip
from database import SessionLocal, get_db
from models.audit_log import AuditLog


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
AUTH_PATHS = {"/api/auth/login", "/auth/login", "/api/auth/register"}
logger = logging.getLogger(__name__)


def _persist_audit(app, values: dict, method: str, path: str) -> None:
    """Run synchronous SQLAlchemy work outside the ASGI event loop."""
    override = app.dependency_overrides.get(get_db)
    generator: Generator | None = None
    db = None
    try:
        if override is not None:
            generator = override()
            db = next(generator)
        else:
            db = SessionLocal()
        db.add(AuditLog(**values))
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception(
            "Unable to persist audit metadata for %s %s",
            method,
            path,
        )
    finally:
        if generator is not None:
            generator.close()
        elif db is not None:
            db.close()


def _classify_action(method: str, path: str) -> str:
    normalized_path = path.rstrip("/") or "/"
    if normalized_path.startswith("/api/v2/"):
        if normalized_path.endswith("/check-in"):
            return "CHECK_IN"
        if normalized_path.endswith("/check-out"):
            return "CHECK_OUT"
        if "/vision/" in normalized_path:
            return "VISION_REVIEW" if normalized_path.endswith("/review") else "VISION_CAPTURE" if method == "POST" else "VISION_DELETE"
        if "/cash-shifts" in normalized_path:
            return "SHIFT_CLOSE" if normalized_path.endswith("/close") else "SHIFT_OPEN"
        if normalized_path.endswith("/collect"):
            return "PAYMENT_COLLECT"
        if normalized_path.endswith("/simulate"):
            return "PAYMENT_DEMO"
        if "/refund" in normalized_path:
            return "REFUND"
        if "/reservations" in normalized_path or "/waitlist" in normalized_path:
            return "RESERVATION_ACTION"
    if normalized_path in {"/api/auth/login", "/auth/login"}:
        return "LOGIN"
    if normalized_path == "/api/auth/register":
        return "REGISTER"
    if normalized_path in {
        "/parking/check-in",
        "/api/v1/parking-sessions/check-in",
    }:
        return "CHECK_IN"
    if normalized_path == "/parking/check-out" or re.fullmatch(
        r"/api/v1/parking-sessions/[^/]+/check-out",
        normalized_path,
    ):
        return "CHECK_OUT"
    if path.startswith("/ai/"):
        return "AI_ACTION"
    return {"POST": "CREATE", "PUT": "UPDATE", "PATCH": "UPDATE", "DELETE": "DELETE"}[method]


def _extract_resource(path: str) -> tuple[str, str | None]:
    parts = [part for part in path.split("/") if part]
    if parts[:2] == ["api", "v2"]:
        tail = parts[2:]
        if tail[:1] == ["sites"] and len(tail) > 2:
            tail = tail[2:]
        elif tail[:1] in (["me"], ["vision"], ["portal"]):
            tail = tail[2:] if tail[:2] == ["portal", "admin"] else tail[1:]
        resource = tail[0] if tail else "system"
        identity = tail[1] if len(tail) > 1 else None
        return resource, identity if identity and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identity) else None
    if path.startswith("/parking/check-"):
        return "parking-sessions", None
    if path.startswith("/ai/"):
        return "ai", None
    if parts[:2] == ["api", "v1"] and len(parts) >= 3:
        resource = parts[2]
        candidate = parts[3] if len(parts) >= 4 else None
    elif parts[:2] == ["api", "auth"]:
        resource = "account"
        candidate = None
    else:
        resource = parts[0] if parts else "system"
        candidate = parts[-1] if len(parts) > 1 else None

    if candidate and (candidate.isdigit() or re.fullmatch(r"[0-9a-fA-F-]{32,36}", candidate)):
        return resource, candidate
    return resource, None


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Ghi metadata thao tác; không đọc hoặc lưu request body/mật khẩu/mã bí mật."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.method not in MUTATING_METHODS:
            return response
        if response.status_code in {307, 308}:
            return response

        authorization = request.headers.get("authorization", "")
        user_id = None
        username = "anonymous"
        is_public_auth = request.url.path.rstrip("/") in AUTH_PATHS
        # Login/register authenticate their own credentials, not an optional
        # Bearer header. Always account for these attempts anonymously: invalid,
        # expired or stale tokens must not bypass the audit-backed rate limits.
        if not is_public_auth and authorization.lower().startswith("bearer "):
            try:
                payload = jwt.decode(
                    authorization.split(" ", 1)[1],
                    settings.SECRET_KEY,
                    algorithms=[settings.ALGORITHM],
                )
                user_id = int(payload["sub"])
                username = str(payload.get("username") or f"user-{user_id}")
            except (InvalidTokenError, KeyError, TypeError, ValueError):
                return response
        elif not is_public_auth:
            return response

        resource, resource_id = _extract_resource(request.url.path)
        await run_in_threadpool(
            _persist_audit,
            request.app,
            {
                "user_id": user_id,
                "username": username[:50],
                "action": _classify_action(request.method, request.url.path),
                "resource": resource[:80],
                "resource_id": resource_id,
                "request_id": getattr(request.state, "request_id", None),
                "site_id": int(request.path_params["site_id"]) if str(request.path_params.get("site_id", "")).isdigit() else None,
                "duration_ms": max(0, round((monotonic() - getattr(request.state, "started_at", monotonic())) * 1000)),
                "method": request.method,
                "path": request.url.path[:255],
                "status_code": response.status_code,
                "success": 200 <= response.status_code < 400,
                "ip_address": get_client_ip(request),
            },
            request.method,
            request.url.path,
        )
        return response
