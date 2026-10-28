"""Security response headers shared by every API route and error response.

The demo server's SPA shell and assets get the frontend variant (review
28/10/2026 A-13): HSTS, nosniff, DENY framing, the referrer policy and
``camera=(self)`` for the camera page, as the production frontend proxy sends. The production Content-Security-Policy and
Cross-Origin-Opener-Policy are deliberately not sent here: the demo is served
over plain HTTP on a LAN for phone cameras, where the production CSP's
``upgrade-insecure-requests`` would break every asset, and its ``connect-src``
names the production API host.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def apply_security_headers(headers, path: str) -> None:
    headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if path.startswith(("/api/", "/auth/", "/ai/", "/parking/", "/dashboard", "/reports")):
        headers.setdefault("Cache-Control", "no-store")


def apply_frontend_security_headers(headers, path: str) -> None:
    headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, frontend: bool = False) -> None:
        self.app = app
        # setdefault: an API response mounted below keeps its stricter headers.
        self.apply = apply_frontend_security_headers if frontend else apply_security_headers

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                self.apply(headers, path)
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
