"""Proactive vault organizer — top-level Deep Agent."""

from __future__ import annotations

import argparse
import asyncio
import os

from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

from .config import AgentConfig
from .prompts import LINKER_INSTRUCTIONS, ORGANIZER_INSTRUCTIONS, TAGGER_INSTRUCTIONS
from .tools import load_vault_tools


def _configure_langsmith(cfg: AgentConfig) -> None:
    if cfg.langsmith_tracing:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", cfg.langsmith_project)


async def build_organizer(cfg: AgentConfig | None = None):
    cfg = cfg or AgentConfig()
    _configure_langsmith(cfg)

    tools = await load_vault_tools(cfg.mcp_url, cfg.mcp_static_token or None)
    model = init_chat_model(cfg.model)

    subagents = [
        {
            "name": "linker",
            "description": (
                "Discover candidate [[wikilinks]] for a given note. Does not modify the vault."
            ),
            "prompt": LINKER_INSTRUCTIONS,
            "tools": [
                t.name
                for t in tools
                if t.name in {"vault_read", "find_link_candidates", "list_outgoing_links"}
            ],
        },
        {
            "name": "tagger",
            "description": (
                "Propose frontmatter tags for a note, aligned with the existing taxonomy."
            ),
            "prompt": TAGGER_INSTRUCTIONS,
            "tools": [
                t.name for t in tools if t.name in {"vault_read", "list_all_notes"}
            ],
        },
    ]

    return create_deep_agent(
        tools=tools,
        instructions=ORGANIZER_INSTRUCTIONS,
        subagents=subagents,
        model=model,
    )


async def run_organizer_pass(prompt: str | None = None) -> dict:
    agent = await build_organizer()
    user_msg = prompt or (
        "Run one proactive organization pass over the vault. Focus on notes in `Inbox/` "
        "and notes with fewer than 2 outgoing wikilinks. Apply at most 10 changes total."
    )
    return await agent.ainvoke({"messages": [{"role": "user", "content": user_msg}]})


def cli() -> None:
    parser = argparse.ArgumentParser(prog="vault-organizer")
    parser.add_argument("--prompt", help="Override the default organization prompt.")
    args = parser.parse_args()
    result = asyncio.run(run_organizer_pass(args.prompt))
    final = result["messages"][-1] if result.get("messages") else result
    print(getattr(final, "content", str(final)))  # noqa: T201


if __name__ == "__main__":
    cli()
