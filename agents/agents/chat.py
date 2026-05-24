"""Conversational agent over the vault, with token streaming.

Lighter than the organizer: no sub-agents, read/search/link tools available so
the user can ask questions and request edits interactively.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from .config import AgentConfig
from .tools import load_vault_tools

load_dotenv()

CHAT_INSTRUCTIONS = """\
You are a helpful assistant connected to a personal Obsidian vault.

You can read, search, and (when asked) edit notes, and discover [[wikilinks]]
between them. Answer questions about the vault concisely. Before editing,
briefly say what you'll change. Note paths are vault-relative and end in `.md`.
"""


async def build_chat_agent(cfg: AgentConfig | None = None):
    cfg = cfg or AgentConfig()
    tools = await load_vault_tools(cfg.mcp_url, cfg.mcp_static_token or None)
    model = init_chat_model(cfg.model)
    return create_deep_agent(model=model, tools=tools, system_prompt=CHAT_INSTRUCTIONS)


def _chunk_text(message) -> str:
    """Extract incremental text from a streamed message chunk."""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


async def astream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """Yield response text tokens from the chat agent as they are generated."""
    agent = await build_chat_agent()
    async for item in agent.astream(
        {"messages": messages},
        stream_mode="messages",
        subgraphs=True,
    ):
        # With subgraphs=True: item = (namespace_tuple, (message_chunk, metadata))
        payload = item[1] if isinstance(item, tuple) and len(item) == 2 else item
        message = payload[0] if isinstance(payload, tuple) else payload
        # Only stream the assistant's own tokens, not tool results.
        if getattr(message, "type", "") not in {"AIMessageChunk", "ai"}:
            continue
        text = _chunk_text(message)
        if text:
            yield text
