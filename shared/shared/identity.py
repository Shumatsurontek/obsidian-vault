"""Identity extractor for FastMCP Context: prefers OAuth claims, falls back to
``X-User-*`` headers.
"""

from __future__ import annotations

import contextlib
from typing import Any


def extract_request_identity(ctx: Any) -> dict[str, Any]:
    identity = {"user_email": None, "user_name": None, "user_id": None, "mcp_client": None}
    if ctx is None:
        return identity

    with contextlib.suppress(Exception):
        token = getattr(ctx, "access_token", None) or getattr(ctx, "token", None)
        claims = getattr(token, "claims", None) if token else None
        if claims:
            identity["user_email"] = claims.get("email") or claims.get("sub")
            identity["user_name"] = claims.get("name")
            identity["user_id"] = claims.get("sub")

    with contextlib.suppress(Exception):
        request = getattr(ctx, "request", None)
        headers = getattr(request, "headers", {}) if request else {}
        identity["user_email"] = identity["user_email"] or headers.get("x-user-email")
        identity["user_name"] = identity["user_name"] or headers.get("x-user-name")
        identity["user_id"] = identity["user_id"] or headers.get("x-user-id")
        identity["mcp_client"] = headers.get("user-agent")

    return identity
