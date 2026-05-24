"""Entry point for the vault MCP server."""

from __future__ import annotations

import argparse

from fastmcp import FastMCP
from shared.logging import setup_logging

from .client import VaultClient
from .config import Config
from .tools import register_all_tools

INSTRUCTIONS = """\
You are connected to a personal Obsidian vault via direct filesystem access.

Use the tools to:
- Read, write, append, delete, and search notes (text + semantic).
- Discover and create [[wikilinks]]; find similar notes by meaning.
- Manage the tag taxonomy (list, rename, merge) and frontmatter.
- Move/rename notes WITHOUT breaking links (backlinks are rewritten).
- Inspect graph health (orphans, unresolved links, stats) and recency.
- Instantiate notes from templates and create daily notes.

Conventions:
- Note paths are vault-relative (no leading slash). Always include the `.md`
  suffix when reading/writing.
- Prefer `semantic_search` / `find_similar_notes` for relevance, `search_simple`
  for exact strings.
- Before adding a wikilink, call `list_outgoing_links` to avoid duplicates.
- To reorganize, use `move_note` (never delete+recreate) so links stay intact.
- Batch changes per note: read once, plan, apply.
"""


def build_server(cfg: Config) -> tuple[FastMCP, VaultClient]:
    setup_logging(cfg.log_level, cfg.log_format)
    client = VaultClient(cfg.vault_path)
    mcp = FastMCP(name="obsidian-vault", instructions=INSTRUCTIONS)
    register_all_tools(mcp, client, cfg)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(_request):  # pragma: no cover
        from starlette.responses import PlainTextResponse

        return PlainTextResponse("OK")

    return mcp, client


def cli() -> None:
    parser = argparse.ArgumentParser(prog="obsidian-mcp")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "http", "sse"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    cfg = Config()
    mcp, _client = build_server(cfg)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    cli()
