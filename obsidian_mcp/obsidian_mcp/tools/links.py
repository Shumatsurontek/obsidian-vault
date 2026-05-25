"""Higher-level tools for hyperlink discovery and proactive organization."""

from __future__ import annotations

import re
from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient
from ..wikilinks import WIKILINK, extract_targets

# A heading (any level) whose text mentions "Related" — e.g. "## Related",
# "## Related notes", "## 14. Related notes". Matched case-insensitively.
_RELATED_HEADING = re.compile(r"^#{1,6}\s+.*\bRelated\b.*$", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s")
_LIST_ITEM = re.compile(r"^\s*[-*+]\s+")


def insert_related_link(content: str, link: str) -> str:
    """Add ``- {link}`` to the note's Related section without disturbing spacing.

    Appends after the last bullet of an existing ``*Related*`` heading (whatever
    its exact wording/level). If no such section exists, a fresh ``## Related``
    block is appended. Idempotency is the caller's concern.
    """
    bullet = f"- {link}"
    lines = content.splitlines()
    heading = next((i for i, ln in enumerate(lines) if _RELATED_HEADING.match(ln)), None)

    if heading is None:
        return f"{content.rstrip()}\n\n## Related\n\n{bullet}\n"

    # Walk the section body (until the next heading or EOF), tracking its last bullet.
    last_item = None
    j = heading + 1
    while j < len(lines) and not _HEADING.match(lines[j]):
        if _LIST_ITEM.match(lines[j]):
            last_item = j
        j += 1

    if last_item is not None:
        lines.insert(last_item + 1, bullet)
    elif heading + 1 < len(lines) and lines[heading + 1].strip() == "":
        lines.insert(heading + 2, bullet)  # blank line already separates heading
    else:
        lines.insert(heading + 1, "")
        lines.insert(heading + 2, bullet)

    text = "\n".join(lines)
    return text + "\n" if content.endswith("\n") else text


def remove_link(content: str, target: str, *, title_of) -> tuple[str, int]:
    """Strip every ``[[target...]]`` (case-insensitive, alias/heading aware).

    ``title_of`` normalizes a link target to its comparison key (basename,
    case-folded) — pass ``VaultClient.link_key``. Bullets left empty by the
    removal are dropped. Returns ``(new_content, removed_count)``.
    """
    key = title_of(target)
    removed = 0

    def repl(m: re.Match) -> str:
        nonlocal removed
        if title_of(m.group(1).strip()) == key:
            removed += 1
            return ""
        return m.group(0)

    new = WIKILINK.sub(repl, content)
    if removed:
        new = re.sub(r"^[ \t]*[-*+][ \t]*$\n?", "", new, flags=re.MULTILINE)
    return new, removed


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
        return sorted(set(extract_targets(client.read_note(path))))

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
            "Insert a [[target_title]] wikilink into a note. With `anchor_text`, the link is "
            "added inline after its first occurrence; otherwise it is appended to the note's "
            "Related section (any '*Related*' heading is reused, else one is created). "
            "Idempotent: a link to the same note (case-insensitive) is not duplicated."
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

        existing = {client.link_key(t) for t in extract_targets(content)}
        if client.link_key(target_title) in existing:
            return {"path": path, "status": "already_linked", "target": target_title}

        if anchor_text and anchor_text in content:
            new_content = content.replace(anchor_text, f"{anchor_text} ({link})", 1)
            client.write_note(path, new_content)
            return {"path": path, "status": "inlined", "target": target_title}

        client.write_note(path, insert_related_link(content, link))
        return {"path": path, "status": "appended_related", "target": target_title}

    @mcp.tool(
        description=(
            "Remove every [[target]] wikilink from a note (case-insensitive, alias/heading "
            "aware). Bullets left empty by the removal are cleaned up. The inverse of "
            "add_wikilink; use it to undo a single link without rewriting the whole note."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="links")
    async def remove_wikilink(
        path: str, target: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        content = client.read_note(path)
        new_content, removed = remove_link(content, target, title_of=client.link_key)
        if removed:
            client.write_note(path, new_content)
        status = "removed" if removed else "not_found"
        return {"path": path, "status": status, "target": target, "removed": removed}

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
