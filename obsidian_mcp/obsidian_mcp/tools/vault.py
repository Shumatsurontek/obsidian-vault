"""Vault read/write/search tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient


def register_vault_tools(mcp: FastMCP, client: VaultClient) -> None:
    @mcp.tool(
        description="List files and folders in the vault, optionally scoped to a sub-directory.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="vault")
    async def vault_list(directory: str = "", ctx: Context | None = None) -> list[str]:
        """List the contents of the vault root or a sub-directory.

        Args:
            directory: Optional sub-directory inside the vault. Empty = vault root.
        """
        return client.list_vault(directory)

    @mcp.tool(
        description="Read the markdown content of a note by its vault-relative path.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="vault")
    async def vault_read(path: str, ctx: Context | None = None) -> str:
        """Read a note. ``path`` is vault-relative, e.g. ``Inbox/today.md``."""
        return client.read_note(path)

    @mcp.tool(description="Overwrite (or create) a note with the supplied markdown content.")
    @traced_tool(mcp_server="obsidian", category="vault")
    async def vault_write(path: str, content: str, ctx: Context | None = None) -> dict[str, str]:
        """Create or replace a note at ``path``."""
        client.write_note(path, content)
        return {"path": path, "status": "written"}

    @mcp.tool(description="Append markdown content to the end of an existing note.")
    @traced_tool(mcp_server="obsidian", category="vault")
    async def vault_append(path: str, content: str, ctx: Context | None = None) -> dict[str, str]:
        """Append to a note (creates it if absent)."""
        client.append_note(path, content)
        return {"path": path, "status": "appended"}

    @mcp.tool(description="Delete a note from the vault.")
    @traced_tool(mcp_server="obsidian", category="vault")
    async def vault_delete(path: str, ctx: Context | None = None) -> dict[str, str]:
        client.delete_note(path)
        return {"path": path, "status": "deleted"}

    @mcp.tool(
        description=(
            "Set a frontmatter key on a note (creates the YAML block if absent). "
            "Used by the tagger sub-agent."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="vault")
    async def vault_set_frontmatter(
        path: str, key: str, value: str, ctx: Context | None = None
    ) -> dict[str, str]:
        client.patch_frontmatter(path, key, value)
        return {"path": path, "status": "frontmatter_set", "key": key}

    @mcp.tool(
        description="Full-text search across the vault. Returns matches with snippets.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="search")
    async def search_simple(
        query: str,
        context_length: int = 100,
        limit: int = 25,
        ctx: Context | None = None,
    ) -> list[dict[str, Any]]:
        return client.search_simple(query, context_length=context_length, limit=limit)

    @mcp.tool(
        description="Return the full list of markdown notes in the vault.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="vault")
    async def list_all_notes(ctx: Context | None = None) -> list[str]:
        return client.list_all_notes()
