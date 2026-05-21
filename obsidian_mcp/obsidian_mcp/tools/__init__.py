"""Tools for the vault MCP server."""

from .links import register_links_tools
from .vault import register_vault_tools

__all__ = ["register_links_tools", "register_vault_tools"]


def register_all_tools(mcp, client) -> None:
    register_vault_tools(mcp, client)
    register_links_tools(mcp, client)
