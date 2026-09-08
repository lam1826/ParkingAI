"""Bounded correlation IDs and request timing; no request body/query/token logging."""
from contextvars import ContextVar
import json
import logging
import re
from time import monotonic
from uuid import uuid4
import traceback
from pathlib import Path

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from middleware.security_headers import apply_security_headers

request_id_context = ContextVar("parkingai_request_id", default=None)
logger = logging.getLogger("parkingai.requests")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        supplied = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied if VALID_ID.fullmatch(supplied) else uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state["started_at"] = monotonic()
        token = request_id_context.set(request_id)
        status = 500
        response_started = False

        async def tracked_send(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as error:
            frames = traceback.extract_tb(error.__traceback__)
            last = frames[-1] if frames else None
            logger.error(json.dumps({"event": "unhandled_request_error", "request_id": request_id,
                "error_type": type(error).__name__, "source": f"{Path(last.filename).name}:{last.lineno}" if last else None}))
            if response_started:
                raise
            headers = {"Cache-Control": "no-store"}
            apply_security_headers(headers, str(scope.get("path", "")))
            from core.config import settings
            origin = Headers(scope=scope).get("origin")
            if origin and origin in {value.strip() for value in settings.CORS_ORIGINS.split(",")}:
                headers.update({"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true",
                                "Access-Control-Expose-Headers": "X-Request-ID", "Vary": "Origin"})
            await JSONResponse({"detail": "Hệ thống chưa xử lý được yêu cầu. Vui lòng thử lại hoặc cung cấp mã truy vết để được hỗ trợ.",
                                "request_id": request_id}, status_code=500, headers=headers)(scope, receive, tracked_send)
        finally:
            # Use the matched route template, never IDs or URL query strings.
            route = getattr(scope.get("route"), "path", "<unmatched>")
            record = {"event": "http_request", "request_id": request_id, "method": scope.get("method"),
                      "route": route, "status": status, "duration_ms": round((monotonic() - state["started_at"]) * 1000)}
            logger.log(logging.WARNING if status >= 400 else logging.INFO, json.dumps(record))
            request_id_context.reset(token)
