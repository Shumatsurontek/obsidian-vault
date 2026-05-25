"""Self-contained demo of obsidian-vault-mcp, recorded as the README GIF.

Runs REAL MCP tool calls through an in-memory FastMCP client against a throwaway
vault — discovers a missing link, adds it (idempotently), then shows the
auto-snapshot undo net. No API keys required; this exercises the tool layer.

Recorded via `vhs docs/demo.tape`.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

DIM = "\033[2m"
B = "\033[1m"
G = "\033[32m"
C = "\033[36m"
Y = "\033[33m"
X = "\033[0m"


def line(s: str = "") -> None:
    print(s, flush=True)


def beat(s: float = 0.9) -> None:
    time.sleep(s)


def prompt(cmd: str) -> None:
    print(f"{G}❯{X} {cmd}", flush=True)
    beat(0.6)


async def main() -> None:
    vault = Path(tempfile.mkdtemp(prefix="demo-vault-"))
    os.environ.update(
        VAULT_PATH=str(vault), OPENAI_API_KEY="", MCP_STATIC_TOKEN="", LOG_LEVEL="CRITICAL"
    )
    (vault / "Attention.md").write_text("# Attention\n\nScaled dot-product attention.\n")
    (vault / "Transformers.md").write_text("# Transformers\n\nBuilt on attention.\n")

    from fastmcp import Client
    from obsidian_mcp.config import Config
    from obsidian_mcp.server import build_server

    mcp, _client = build_server(Config())

    line(f"{B}{C}obsidian-vault-mcp{X} {DIM}— an agent that curates your Obsidian vault{X}")
    line()
    beat()
    prompt("vault: 2 related notes, 0 links between them")
    line(f"  {DIM}Attention.md     Transformers.md{X}")
    beat()
    line()

    async with Client(mcp) as c:
        prompt('add_wikilink   Attention.md → "Transformers"')
        await c.call_tool("add_wikilink", {"path": "Attention.md", "target_title": "Transformers"})
        line(f"  {G}✓{X} linked, under a Related section:")
        tail = [ln for ln in (vault / "Attention.md").read_text().splitlines() if ln.strip()][-2:]
        for ln in tail:
            line(f"    {DIM}{ln}{X}")
        beat(1.1)
        line()

        prompt('add_wikilink   Attention.md → "Transformers"   (again)')
        res = await c.call_tool(
            "add_wikilink", {"path": "Attention.md", "target_title": "Transformers"}
        )
        line(f"  {Y}↪ {res.data['status']}{X}  {DIM}idempotent — no duplicate{X}")
        beat(1.1)
        line()

        prompt("undo the whole pass")
        await c.call_tool("undo_last_pass", {})
        restored = "[[Transformers]]" not in (vault / "Attention.md").read_text()
        msg = "every write is git-snapshotted automatically"
        line(f"  {G}✓ restored{X}  {DIM}{msg}{X}" if restored else "  restore failed")
        beat(1.3)
        line()

    line(f"{DIM}35 tools · FastMCP · LangGraph · auto-snapshot/undo{X}")
    line(f"{C}github.com/Shumatsurontek/obsidian-vault{X}")
    beat(1.4)


if __name__ == "__main__":
    asyncio.run(main())
