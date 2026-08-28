import re
from collections.abc import Generator

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.config import settings
from database import SessionLocal, get_db
from models.audit_log import AuditLog


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _classify_action(method: str, path: str) -> str:
    normalized_path = path.rstrip("/") or "/"
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
        if not authorization.lower().startswith("bearer "):
            return response

        try:
            payload = jwt.decode(
                authorization.split(" ", 1)[1],
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
            user_id = int(payload["sub"])
            username = str(payload.get("username") or f"user-{user_id}")
        except (JWTError, KeyError, TypeError, ValueError):
            return response

        resource, resource_id = _extract_resource(request.url.path)
        override = request.app.dependency_overrides.get(get_db)
        generator: Generator | None = None
        db = None
        try:
            if override is not None:
                generator = override()
                db = next(generator)
            else:
                db = SessionLocal()
            db.add(AuditLog(
                user_id=user_id,
                username=username[:50],
                action=_classify_action(request.method, request.url.path),
                resource=resource[:80],
                resource_id=resource_id,
                method=request.method,
                path=request.url.path[:255],
                status_code=response.status_code,
                success=200 <= response.status_code < 400,
                ip_address=request.client.host if request.client else None,
            ))
            db.commit()
        except Exception:
            if db is not None:
                db.rollback()
        finally:
            if generator is not None:
                generator.close()
            elif db is not None:
                db.close()
        return response
