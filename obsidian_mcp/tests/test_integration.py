"""End-to-end tests through the real FastMCP tool layer (in-memory client).

These exercise the wiring that the pure-helper tests can't: tool registration,
the auto-snapshot net firing on writes, and undo — all via actual tool calls.
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from obsidian_mcp.config import Config
from obsidian_mcp.server import build_server


@pytest.fixture
def mcp_and_vault(tmp_path, monkeypatch):
    # Env vars beat the repo .env in pydantic-settings, so this points Config at
    # the temp vault, never Arthur's real one. The assertion below is a hard stop.
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "")  # keep semantic tools disabled
    monkeypatch.setenv("MCP_STATIC_TOKEN", "")
    (tmp_path / "a.md").write_text("# A\n\nbody\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n\nbody\n", encoding="utf-8")

    mcp, client = build_server(Config())
    assert client.root == tmp_path.resolve()  # never operate on the real vault
    return mcp, tmp_path


async def test_add_idempotent_remove_then_undo(mcp_and_vault):
    mcp, root = mcp_and_vault
    a = root / "a.md"

    async with Client(mcp) as c:
        await c.call_tool("add_wikilink", {"path": "a.md", "target_title": "B"})
        assert "[[B]]" in a.read_text()

        # Idempotent: a second add must not duplicate the link.
        await c.call_tool("add_wikilink", {"path": "a.md", "target_title": "B"})
        assert a.read_text().count("[[B]]") == 1

        await c.call_tool("remove_wikilink", {"path": "a.md", "target": "B"})
        assert "[[B]]" not in a.read_text()

        # Every write above is one debounced batch; undo restores the baseline.
        await c.call_tool("undo_last_pass", {})
        assert a.read_text() == "# A\n\nbody\n"


async def test_add_wikilink_reports_already_linked(mcp_and_vault):
    mcp, _root = mcp_and_vault
    async with Client(mcp) as c:
        await c.call_tool("add_wikilink", {"path": "a.md", "target_title": "B"})
        res = await c.call_tool("add_wikilink", {"path": "a.md", "target_title": "B"})
        assert res.data["status"] == "already_linked"


async def test_delete_then_undo_restores_note(mcp_and_vault):
    mcp, root = mcp_and_vault
    async with Client(mcp) as c:
        await c.call_tool("vault_delete", {"path": "b.md"})
        assert not (root / "b.md").exists()
        await c.call_tool("undo_last_pass", {})
        assert (root / "b.md").read_text() == "# B\n\nbody\n"
