"""Semantic search & similarity tools (embeddings-powered)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient
from ..semantic_index import SemanticIndex

_NO_KEY = {
    "status": "error",
    "error": "OPENAI_API_KEY not set — semantic tools are disabled.",
}


def register_semantic_tools(mcp: FastMCP, client: VaultClient, cfg) -> None:
    index: SemanticIndex | None = (
        SemanticIndex(client, api_key=cfg.openai_api_key, model=cfg.embedding_model)
        if cfg.openai_api_key
        else None
    )

    @mcp.tool(
        description=(
            "Semantic search across the vault by meaning (embeddings), not just substring. "
            "Returns the top-k most relevant notes with similarity scores."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="semantic")
    async def semantic_search(
        query: str, k: int = 5, ctx: Context | None = None
    ) -> list[dict[str, Any]] | dict[str, Any]:
        if index is None:
            return _NO_KEY
        return index.search(query, k=k)

    @mcp.tool(
        description=(
            "Find notes semantically similar to a given note (good for discovering "
            "[[wikilink]] candidates by meaning). Returns top-k with scores."
        ),
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="semantic")
    async def find_similar_notes(
        path: str, k: int = 5, ctx: Context | None = None
    ) -> list[dict[str, Any]] | dict[str, Any]:
        if index is None:
            return _NO_KEY
        if not client.exists(path):
            return {"status": "error", "error": f"note not found: {path}"}
        return index.similar(path, k=k)

    @mcp.tool(
        description="Rebuild the embedding index (incremental: only new/changed notes).",
    )
    @traced_tool(mcp_server="obsidian", category="semantic")
    async def reindex_embeddings(ctx: Context | None = None) -> dict[str, Any]:
        if index is None:
            return _NO_KEY
        return index.refresh()
