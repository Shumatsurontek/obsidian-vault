"""Tag taxonomy tools."""

from __future__ import annotations

import re
from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from .. import frontmatter as fm
from ..client import VaultClient


def register_tag_tools(mcp: FastMCP, client: VaultClient) -> None:
    @mcp.tool(
        description=(
            "Return the vault tag vocabulary with usage counts (frontmatter + inline #tags), "
            "most used first."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="tags")
    async def list_tags(ctx: Context | None = None) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for path in client.iter_note_paths():
            for tag in fm.note_tags(client.read_note(path)):
                counts[tag] = counts.get(tag, 0) + 1
        return [
            {"tag": t, "count": c}
            for t, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ]

    @mcp.tool(
        description="List notes carrying a given tag (frontmatter or inline).",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="tags")
    async def get_notes_by_tag(tag: str, ctx: Context | None = None) -> list[str]:
        wanted = tag.lstrip("#")
        return sorted(
            p for p in client.iter_note_paths() if wanted in fm.note_tags(client.read_note(p))
        )

    @mcp.tool(
        description="Return the parsed YAML frontmatter of a note as a dict.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="tags")
    async def get_frontmatter(path: str, ctx: Context | None = None) -> dict[str, Any]:
        data, _ = fm.parse(client.read_note(path))
        return data

    @mcp.tool(
        description=(
            "Rename a tag across the whole vault (frontmatter `tags` and inline #tags). "
            "Returns the notes updated."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="tags")
    async def rename_tag(
        old: str, new: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        return _bulk_retag(client, {old.lstrip("#")}, new.lstrip("#"))

    @mcp.tool(
        description=(
            "Merge several tags into one across the vault (frontmatter + inline). "
            "sources is a list of tag names; they all become `target`."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="tags")
    async def merge_tags(
        sources: list[str], target: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        return _bulk_retag(client, {s.lstrip("#") for s in sources}, target.lstrip("#"))


def _bulk_retag(client: VaultClient, olds: set[str], new: str) -> dict[str, Any]:
    touched: list[str] = []
    for path in client.iter_note_paths():
        content = client.read_note(path)
        data, body = fm.parse(content)
        changed = False

        # frontmatter tags
        if "tags" in data:
            current = fm.normalize_tags(data.get("tags"))
            updated = [new if t in olds else t for t in current]
            deduped = list(dict.fromkeys(updated))
            if deduped != current:
                data["tags"] = deduped
                changed = True

        # inline #tags in body
        new_body = body
        for old in olds:
            pattern = re.compile(rf"(?<![\w/])#{re.escape(old)}(?![\w\-/])")
            new_body, n = pattern.subn(f"#{new}", new_body)
            if n:
                changed = True

        if changed:
            client.write_note(path, fm.dump(data, new_body) if data else new_body)
            touched.append(path)

    return {"status": "retagged", "from": sorted(olds), "to": new, "notes_updated": touched}
