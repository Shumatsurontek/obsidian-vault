"""Graph-health & link-integrity tools."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient
from ..wikilinks import extract_targets, rewrite_target


def _build_link_graph(
    client: VaultClient,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, str]]:
    """Return (outgoing, incoming, display) keyed by case-folded link key.

    Link resolution is case-insensitive, matching Obsidian. `display` maps a key
    back to the note's actual basename for rendering.
    """
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    for path in client.iter_note_paths():
        key = client.link_key(path)
        display[key] = client.basename(path)
        outgoing.setdefault(key, set())
        incoming.setdefault(key, set())
    for path in client.iter_note_paths():
        key = client.link_key(path)
        try:
            targets = extract_targets(client.read_note(path))
        except OSError:
            continue
        for tgt in targets:
            tkey = client.link_key(tgt)
            display.setdefault(tkey, client.basename(tgt))
            outgoing[key].add(tkey)
            incoming.setdefault(tkey, set()).add(key)
    return outgoing, incoming, display


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
        outgoing, incoming, _ = _build_link_graph(client)
        orphans = []
        for path in client.iter_note_paths():
            key = client.link_key(path)
            if not outgoing.get(key) and not incoming.get(key):
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
        existing = {client.link_key(p) for p in client.iter_note_paths()}
        unresolved: dict[str, set[str]] = {}
        for path in client.iter_note_paths():
            for tgt in extract_targets(client.read_note(path)):
                if client.link_key(tgt) not in existing:
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
        outgoing, incoming, _ = _build_link_graph(client)
        note_keys = {client.link_key(p) for p in client.iter_note_paths()}
        note_count = sum(1 for _ in client.iter_note_paths())
        total_links = sum(len(v) for v in outgoing.values())
        orphans = sum(
            1 for k in note_keys if not outgoing.get(k) and not incoming.get(k)
        )
        unresolved = 0
        for path in client.iter_note_paths():
            for tgt in extract_targets(client.read_note(path)):
                if client.link_key(tgt) not in note_keys:
                    unresolved += 1
        return {
            "notes": note_count,
            "total_links": total_links,
            "orphans": orphans,
            "unresolved_links": unresolved,
            "avg_links_per_note": round(total_links / note_count, 2) if note_count else 0,
        }

    @mcp.tool(
        description=(
            "Export the note link graph. format='mermaid' returns a Mermaid diagram string; "
            "format='json' returns {nodes, edges}. Only resolved links are included."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="graph")
    async def export_graph(
        fmt: str = "mermaid", ctx: Context | None = None
    ) -> dict[str, Any]:
        outgoing, _, display = _build_link_graph(client)
        note_keys = {client.link_key(p) for p in client.iter_note_paths()}
        edges = [
            (display[src], display[dst])
            for src, dsts in outgoing.items()
            if src in note_keys
            for dst in dsts
            if dst in note_keys
        ]
        nodes = sorted(display[k] for k in note_keys)
        if fmt == "json":
            return {"nodes": nodes, "edges": [list(e) for e in edges]}

        def nid(name: str) -> str:
            return "n_" + "".join(c if c.isalnum() else "_" for c in name)

        lines = ["graph TD"]
        lines.extend(f'    {nid(name)}["{name}"]' for name in nodes)
        lines.extend(f"    {nid(src)} --> {nid(dst)}" for src, dst in edges)
        return {"format": "mermaid", "diagram": "\n".join(lines), "edge_count": len(edges)}

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
