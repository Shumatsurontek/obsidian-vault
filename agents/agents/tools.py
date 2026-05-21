"""Load the Obsidian MCP server's tools as LangChain tools via langchain-mcp-adapters."""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


async def load_vault_tools(mcp_url: str, token: str | None = None) -> list[BaseTool]:
    """Connect to the running Obsidian MCP HTTP server and return its tools."""
    connections: dict = {
        "obsidian": {
            "url": mcp_url,
            "transport": "streamable_http",
        }
    }
    if token:
        connections["obsidian"]["headers"] = {"Authorization": f"Bearer {token}"}

    client = MultiServerMCPClient(connections)
    return await client.get_tools()
