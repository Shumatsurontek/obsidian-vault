"""Proactive vault organizer — top-level Deep Agent."""

from __future__ import annotations

import argparse
import asyncio
import os

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from .config import AgentConfig
from .prompts import LINKER_INSTRUCTIONS, ORGANIZER_INSTRUCTIONS, TAGGER_INSTRUCTIONS
from .tools import load_vault_tools

# Populate os.environ from .env so provider SDKs (OpenAI, Anthropic, …) find their keys.
load_dotenv()


def _configure_langsmith(cfg: AgentConfig) -> None:
    if cfg.langsmith_tracing:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", cfg.langsmith_project)


async def build_organizer(cfg: AgentConfig | None = None):
    cfg = cfg or AgentConfig()
    _configure_langsmith(cfg)

    tools = await load_vault_tools(cfg.mcp_url, cfg.mcp_static_token or None)
    model = init_chat_model(cfg.model)
    by_name = {t.name: t for t in tools}

    def pick(*names: str) -> list:
        return [by_name[n] for n in names if n in by_name]

    subagents = [
        {
            "name": "linker",
            "description": (
                "Discover candidate [[wikilinks]] for a given note, by meaning and by text. "
                "Does not modify the vault."
            ),
            "system_prompt": LINKER_INSTRUCTIONS,
            "tools": pick(
                "vault_read",
                "find_similar_notes",
                "semantic_search",
                "find_link_candidates",
                "list_outgoing_links",
            ),
            "model": model,
        },
        {
            "name": "tagger",
            "description": (
                "Propose frontmatter tags for a note, aligned with the existing taxonomy."
            ),
            "system_prompt": TAGGER_INSTRUCTIONS,
            "tools": pick("vault_read", "list_tags", "get_frontmatter"),
            "model": model,
        },
    ]

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=ORGANIZER_INSTRUCTIONS,
        subagents=subagents,
    )


async def run_organizer_pass(prompt: str | None = None) -> dict:
    agent = await build_organizer()
    user_msg = prompt or (
        "Run one proactive organization pass. First discover the vault's structure: "
        "call `vault_stats`, `find_orphans`, and `list_recent_notes` — do NOT assume any "
        "folder name exists. Pick a small batch (<= 5) of orphan or recently-edited notes, "
        "improve their links and tags, and apply at most 10 changes total. If a tool returns "
        "an error, adapt and continue rather than stopping."
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
