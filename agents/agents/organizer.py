"""Proactive vault organizer — top-level Deep Agent."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os

from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from .config import AgentConfig
from .prompts import (
    DRY_RUN_INSTRUCTIONS,
    LINKER_INSTRUCTIONS,
    ORGANIZER_INSTRUCTIONS,
    TAGGER_INSTRUCTIONS,
)
from .tools import load_vault_tools

# Populate os.environ from .env so provider SDKs (OpenAI, Anthropic, …) find their keys.
load_dotenv()


def _configure_langsmith(cfg: AgentConfig) -> None:
    if cfg.langsmith_tracing:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_PROJECT", cfg.langsmith_project)


# Tools that mutate the vault — excluded in dry-run mode.
WRITE_TOOLS = frozenset(
    {
        "vault_write", "vault_append", "vault_delete", "vault_set_frontmatter",
        "add_wikilink", "move_note", "rename_tag", "merge_tags",
        "create_from_template", "upsert_template", "create_daily_note",
        "snapshot_vault", "undo_last_pass",
    }
)


async def build_organizer(cfg: AgentConfig | None = None, *, dry_run: bool = False):
    cfg = cfg or AgentConfig()
    _configure_langsmith(cfg)

    tools = await load_vault_tools(cfg.mcp_url, cfg.mcp_static_token or None)
    if dry_run:
        tools = [t for t in tools if t.name not in WRITE_TOOLS]
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

    system_prompt = DRY_RUN_INSTRUCTIONS if dry_run else ORGANIZER_INSTRUCTIONS
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        subagents=subagents,
    )


async def _autosnapshot(cfg: AgentConfig) -> None:
    """Take a restore point before a write pass (best-effort)."""
    tools = await load_vault_tools(cfg.mcp_url, cfg.mcp_static_token or None)
    snap = next((t for t in tools if t.name == "snapshot_vault"), None)
    if snap is not None:
        with contextlib.suppress(Exception):
            await snap.ainvoke({"label": "pre-organizer pass"})


async def run_organizer_pass(prompt: str | None = None, *, dry_run: bool = False) -> dict:
    cfg = AgentConfig()
    if not dry_run:
        await _autosnapshot(cfg)

    agent = await build_organizer(cfg, dry_run=dry_run)
    default = (
        "Run one proactive organization pass. First discover the vault's structure: "
        "call `vault_stats`, `find_orphans`, and `list_recent_notes` — do NOT assume any "
        "folder name exists. Pick a small batch (<= 5) of orphan or recently-edited notes, "
        "{action} at most 10 changes total. If a tool returns an error, adapt and continue."
    )
    if dry_run:
        default = default.format(action="PROPOSE (do not apply)")
    else:
        default = default.format(action="improve their links and tags, applying")
    user_msg = prompt or default
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
