"""Auth scaffolding for the vault MCP server.

Single-user by default: a static bearer token authenticates the operator. Kept
open to swap in an OAuth provider later.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StaticUser:
    email: str
    name: str
    token: str

    @property
    def claims(self) -> dict[str, str]:
        return {"sub": self.email, "email": self.email, "name": self.name}


def build_static_user(token: str | None, email: str, name: str) -> StaticUser | None:
    if not token:
        return None
    return StaticUser(email=email, name=name, token=token)
