"""Graph-health & link-integrity tools."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient
from ..wikilinks import extract_targets, rewrite_target


def _build_link_graph(client: VaultClient) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (outgoing, incoming) maps keyed by note basename."""
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}
    for path in client.iter_note_paths():
        base = client.basename(path)
        outgoing.setdefault(base, set())
        incoming.setdefault(base, set())
    for path in client.iter_note_paths():
        base = client.basename(path)
        try:
            targets = extract_targets(client.read_note(path))
        except OSError:
            continue
        for tgt in targets:
            tgt_base = client.basename(tgt)
            outgoing[base].add(tgt_base)
            incoming.setdefault(tgt_base, set()).add(base)
    return outgoing, incoming


def register_graph_tools(mcp: FastMCP, client: VaultClient) -> None:
    @mcp.tool(
        description=(
            "Rename or move a note and rewrite every [[wikilink]] in the vault that "
            "points to it, so no links break. dest is the new vault-relative path."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="graph")
    async def move_note(
        path: str, dest: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        if not client.exists(path):
            return {"status": "error", "error": f"source not found: {path}"}
        if client.exists(dest):
            return {"status": "error", "error": f"destination exists: {dest}"}

        old_base = client.basename(path)
        new_base = client.basename(dest)

        content = client.read_note(path)
        client.write_note(dest, content)
        client.delete_note(path)

        rewritten = 0
        touched: list[str] = []
        if old_base != new_base:
            for npath in client.iter_note_paths():
                if npath == dest:
                    continue
                text = client.read_note(npath)
                new_text, n = rewrite_target(text, old_base, new_base)
                if n:
                    client.write_note(npath, new_text)
                    rewritten += n
                    touched.append(npath)

        return {
            "status": "moved",
            "from": path,
            "to": dest,
            "links_rewritten": rewritten,
            "notes_updated": touched,
        }

    @mcp.tool(
        description="List notes with no incoming and no outgoing links (orphans).",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="graph")
    async def find_orphans(ctx: Context | None = None) -> list[str]:
        outgoing, incoming = _build_link_graph(client)
        orphans = []
        for path in client.iter_note_paths():
            base = client.basename(path)
            if not outgoing.get(base) and not incoming.get(base):
                orphans.append(path)
        return sorted(orphans)

    @mcp.tool(
        description=(
            "List [[wikilinks]] whose target note does not exist, with the notes that "
            "reference them. These are candidates to create or fix."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="graph")
    async def find_unresolved_links(ctx: Context | None = None) -> list[dict[str, Any]]:
        existing = {client.basename(p) for p in client.iter_note_paths()}
        unresolved: dict[str, set[str]] = {}
        for path in client.iter_note_paths():
            for tgt in extract_targets(client.read_note(path)):
                if client.basename(tgt) not in existing:
                    unresolved.setdefault(tgt, set()).add(path)
        return [
            {"target": tgt, "referenced_by": sorted(refs)}
            for tgt, refs in sorted(unresolved.items())
        ]

    @mcp.tool(
        description="Summary stats: note count, orphan count, unresolved-link count, link totals.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="graph")
    async def vault_stats(ctx: Context | None = None) -> dict[str, Any]:
        outgoing, incoming = _build_link_graph(client)
        existing = set(outgoing)
        note_count = sum(1 for _ in client.iter_note_paths())
        total_links = sum(len(v) for v in outgoing.values())
        orphans = sum(
            1 for b in existing if not outgoing.get(b) and not incoming.get(b)
        )
        unresolved = 0
        for path in client.iter_note_paths():
            for tgt in extract_targets(client.read_note(path)):
                if client.basename(tgt) not in existing:
                    unresolved += 1
        return {
            "notes": note_count,
            "total_links": total_links,
            "orphans": orphans,
            "unresolved_links": unresolved,
            "avg_links_per_note": round(total_links / note_count, 2) if note_count else 0,
        }

    @mcp.tool(
        description="List the most recently modified notes (default 10), newest first.",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="graph")
    async def list_recent_notes(
        limit: int = 10, ctx: Context | None = None
    ) -> list[dict[str, Any]]:
        notes = [(p, client.mtime(p)) for p in client.iter_note_paths()]
        notes.sort(key=lambda x: x[1], reverse=True)
        return [
            {"path": p, "modified": dt.datetime.fromtimestamp(m).isoformat(timespec="seconds")}
            for p, m in notes[:limit]
        ]
