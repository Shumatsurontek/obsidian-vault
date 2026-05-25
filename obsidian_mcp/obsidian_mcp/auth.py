"""Bearer-token auth for the HTTP/SSE transports.

The vault MCP exposes read/write/delete of a personal vault, so the network
transports must not be open. ``stdio`` is local-only and stays unauthenticated;
HTTP/SSE require ``Authorization: Bearer <MCP_STATIC_TOKEN>`` on every request
except the public ``/health`` probe.
"""

from __future__ import annotations

import hmac

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_PUBLIC_PATHS = frozenset({"/health"})


class StaticTokenAuthMiddleware:
    """Reject requests whose Authorization header isn't ``Bearer <token>``."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.url.path in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        provided = request.headers.get("authorization", "")
        # Constant-time compare so a wrong token can't be guessed by timing.
        if not hmac.compare_digest(provided, self._expected):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
