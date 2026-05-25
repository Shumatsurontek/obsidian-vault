"""Tests for the HTTP bearer-token auth middleware."""

from __future__ import annotations

from obsidian_mcp.auth import StaticTokenAuthMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _client() -> TestClient:
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/mcp", ok), Route("/health", ok)])
    app.add_middleware(StaticTokenAuthMiddleware, token="secret")
    return TestClient(app)


def test_rejects_missing_token():
    assert _client().get("/mcp").status_code == 401


def test_rejects_wrong_token():
    resp = _client().get("/mcp", headers={"authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_allows_correct_token():
    resp = _client().get("/mcp", headers={"authorization": "Bearer secret"})
    assert resp.status_code == 200


def test_health_is_public():
    assert _client().get("/health").status_code == 200
