"""Higher-level tools for hyperlink discovery and proactive organization."""

from __future__ import annotations

import re
from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient

# Matches an Obsidian wiki-link: [[Page Name]] or [[Page Name|alias]]
_WIKILINK = re.compile(r"\[\[([^\]\|]+?)(?:\|[^\]]+)?\]\]")


def _extract_wikilinks(markdown: str) -> list[str]:
    return [m.group(1).strip() for m in _WIKILINK.finditer(markdown)]


def register_links_tools(mcp: FastMCP, client: VaultClient) -> None:
    @mcp.tool(
        description=(
            "List every outgoing [[wikilink]] in a note. Use before proposing new "
            "connections to avoid duplicates."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="links")
    async def list_outgoing_links(path: str, ctx: Context | None = None) -> list[str]:
        return sorted(set(_extract_wikilinks(client.read_note(path))))

    @mcp.tool(
        description=(
            "Find candidate notes that mention or relate to a query string. Returns the "
            "top matches with snippets so an LLM can decide where to add links."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="links")
    async def find_link_candidates(
        query: str, limit: int = 10, ctx: Context | None = None
    ) -> list[dict[str, Any]]:
        return client.search_simple(query, context_length=120, limit=limit)

    @mcp.tool(
        description=(
            "Insert a [[target_title]] wikilink near the first occurrence of `anchor_text` "
            "in the note. If `anchor_text` is absent, appends a 'Related' section with the link."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="links")
    async def add_wikilink(
        path: str,
        target_title: str,
        anchor_text: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        content = client.read_note(path)
        link = f"[[{target_title}]]"
        if link in content:
            return {"path": path, "status": "already_linked", "target": target_title}

        if anchor_text and anchor_text in content:
            new_content = content.replace(anchor_text, f"{anchor_text} ({link})", 1)
            client.write_note(path, new_content)
            return {"path": path, "status": "inlined", "target": target_title}

        related_header = "\n\n## Related\n"
        if "## Related" in content:
            new_content = re.sub(
                r"## Related\n", f"## Related\n- {link}\n", content, count=1
            )
        else:
            new_content = content.rstrip() + related_header + f"- {link}\n"
        client.write_note(path, new_content)
        return {"path": path, "status": "appended_related", "target": target_title}

    @mcp.tool(
        description=(
            "Find every note that contains [[target]] (incoming backlinks). Useful before "
            "renaming or restructuring."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="links")
    async def find_backlinks(
        target: str, ctx: Context | None = None
    ) -> list[str]:
        results = client.search_simple(f"[[{target}", limit=200)
        return sorted({r["path"] for r in results})
