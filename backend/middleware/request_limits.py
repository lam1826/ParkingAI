"""Bounded request bodies and strict JSON numbers (review 28/10/2026 R2-04, R2-05).

Every request body is read here before routing, up to ``MAX_REQUEST_BODY_BYTES``
(JSON, forms and multipart alike) and within ``BODY_TIMEOUT_SECONDS``. A larger
body gets 413 and is never parsed or echoed; a body that never completes gets
408; a client that leaves mid-body gets 400, so the application always answers.
A JSON body that writes NaN, Infinity or a number overflowing to infinity gets
422: those are not JSON numbers, and must never reach a model, a money field or
the database. The body is replayed unchanged to the application; nothing is logged.

The camera upload routes (``UPLOAD_PATHS``) are not buffered here: they
authenticate first and then read at most a 2 MB image within 30 s themselves
(``vision_router._read_upload``). Only a declared length above
``MAX_UPLOAD_BODY_BYTES`` is refused before they run.
"""
import asyncio
import json
import math

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

BODY_TOO_LARGE = "Dữ liệu gửi lên vượt giới hạn cho phép."
BODY_TIMEOUT = "Gửi dữ liệu quá thời gian. Hãy thử lại."
BODY_INCOMPLETE = "Kết nối đã đóng trước khi gửi xong dữ liệu."
NON_FINITE_NUMBER = "Dữ liệu JSON không hợp lệ: không chấp nhận NaN, Infinity hoặc số vượt giới hạn."
BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
BODY_TIMEOUT_SECONDS = 30
# Routes that read their own multipart upload after authentication (expansion.vision_router).
UPLOAD_PATHS = {"/api/v2/vision/observations", "/api/v2/vision/live-frames", "/api/v2/vision/edge-events"}


class _NonFinite(ValueError):
    pass


def _reject_constant(_name):
    raise _NonFinite


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise _NonFinite
    return value


def has_non_finite_number(body: bytes) -> bool:
    """True only for valid-looking JSON that uses a non-finite number; other parse errors stay FastAPI's."""
    try:
        json.loads(body, parse_constant=_reject_constant, parse_float=_finite_float)
    except _NonFinite:
        return True
    except (ValueError, RecursionError):
        return False
    return False


def _is_json(content_type: str) -> bool:
    return content_type == "application/json" or content_type.endswith("+json")


def _route_path(scope) -> str:
    path, root = scope.get("path", ""), scope.get("root_path", "")
    return path[len(root):] if root and path.startswith(root) else path


class RequestLimitsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        from core.config import settings
        headers = Headers(scope=scope)
        declared = headers.get("content-length", "")
        if _route_path(scope) in UPLOAD_PATHS:
            if declared.isdigit() and int(declared) > settings.MAX_UPLOAD_BODY_BYTES:
                await JSONResponse({"detail": BODY_TOO_LARGE}, status_code=413)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return
        limit = settings.MAX_REQUEST_BODY_BYTES
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": BODY_TOO_LARGE}, status_code=413)(scope, receive, send)
            return
        # A chunked body has no declared length: count what actually arrives.
        body, more = bytearray(), True
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                while more:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        # The client is gone; answering keeps the middleware chain and
                        # the audit trail on a plain 4xx instead of a missing response.
                        await JSONResponse({"detail": BODY_INCOMPLETE}, status_code=400)(scope, receive, send)
                        return
                    body.extend(message.get("body", b""))
                    more = message.get("more_body", False)
                    if len(body) > limit:
                        await JSONResponse({"detail": BODY_TOO_LARGE}, status_code=413)(scope, receive, send)
                        return
        except TimeoutError:
            await JSONResponse({"detail": BODY_TIMEOUT}, status_code=408)(scope, receive, send)
            return
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if _is_json(content_type) and has_non_finite_number(bytes(body)):
            detail = [{"type": "finite_number", "loc": ["body"], "msg": NON_FINITE_NUMBER}]
            await JSONResponse({"detail": detail}, status_code=422)(scope, receive, send)
            return
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
