"""Vault snapshot / undo tools (git-backed, isolated)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient
from ..git_snapshot import GitSnapshot


def register_snapshot_tools(mcp: FastMCP, client: VaultClient) -> None:
    snap = GitSnapshot(client.root)

    @mcp.tool(
        description=(
            "Take a restore point of the whole vault (git-backed, isolated from any existing "
            ".git). Call before bulk edits so changes can be undone."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="snapshot")
    async def snapshot_vault(
        label: str = "manual snapshot", ctx: Context | None = None
    ) -> dict[str, Any]:
        return snap.snapshot(label)

    @mcp.tool(
        description="List recent vault snapshots (newest first) with sha, timestamp, and label.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="snapshot")
    async def list_snapshots(
        limit: int = 20, ctx: Context | None = None
    ) -> list[dict[str, str]]:
        return snap.list_snapshots(limit=limit)

    @mcp.tool(
        description=(
            "Undo the last organization pass by restoring the vault to the most recent "
            "snapshot. Destructive: discards changes made since that snapshot."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="snapshot")
    async def undo_last_pass(
        sha: str | None = None, ctx: Context | None = None
    ) -> dict[str, Any]:
        return snap.restore(sha)
