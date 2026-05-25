"""Entry point for the vault MCP server."""

from __future__ import annotations

import argparse
import logging

from fastmcp import FastMCP
from shared.logging import setup_logging
from starlette.middleware import Middleware

from .auth import StaticTokenAuthMiddleware
from .client import VaultClient
from .config import Config
from .tools import register_all_tools

logger = logging.getLogger(__name__)

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
- Every mutation auto-creates a restore point; `undo_last_pass` reverts the most
  recent batch of edits, and `remove_wikilink` undoes a single link.
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
        return

    middleware = []
    if cfg.mcp_static_token:
        middleware.append(Middleware(StaticTokenAuthMiddleware, token=cfg.mcp_static_token))
    else:
        logger.warning(
            "MCP_STATIC_TOKEN is not set — the %s server is UNAUTHENTICATED. Anyone who can "
            "reach it can read, write, and delete your vault. Set MCP_STATIC_TOKEN before "
            "exposing it on a network.",
            args.transport,
        )
    mcp.run(
        transport=args.transport,
        host=args.host,
        port=args.port,
        middleware=middleware,
    )


if __name__ == "__main__":
    cli()
