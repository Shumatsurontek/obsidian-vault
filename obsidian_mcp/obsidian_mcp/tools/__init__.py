"""Tools for the vault MCP server."""

from .graph import register_graph_tools
from .links import register_links_tools
from .semantic import register_semantic_tools
from .snapshots import register_snapshot_tools
from .tags import register_tag_tools
from .templates import register_template_tools
from .vault import register_vault_tools

__all__ = [
    "register_graph_tools",
    "register_links_tools",
    "register_semantic_tools",
    "register_snapshot_tools",
    "register_tag_tools",
    "register_template_tools",
    "register_vault_tools",
]


def register_all_tools(mcp, client, cfg) -> None:
    register_vault_tools(mcp, client)
    register_links_tools(mcp, client)
    register_graph_tools(mcp, client)
    register_tag_tools(mcp, client)
    register_template_tools(mcp, client, cfg)
    register_semantic_tools(mcp, client, cfg)
    register_snapshot_tools(mcp, client)
