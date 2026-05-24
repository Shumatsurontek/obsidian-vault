"""Template tools: list, instantiate, manage, and create daily notes."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from fastmcp import Context, FastMCP
from shared.tracing import traced_tool

from ..client import VaultClient

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _find_dir(client: VaultClient, configured: str, pattern: str) -> str | None:
    if configured and client.exists(configured):
        return configured.strip("/")
    pat = re.compile(pattern, re.IGNORECASE)
    for child in client.root.rglob("*"):
        if child.is_dir() and pat.search(child.name):
            if any(p.startswith(".") for p in child.relative_to(client.root).parts):
                continue
            return client.rel(child)
    return None


def _substitute(text: str, variables: dict[str, str]) -> str:
    now = dt.datetime.now()
    builtins = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "datetime": now.strftime("%Y-%m-%d %H:%M"),
        "year": now.strftime("%Y"),
        "month": now.strftime("%m"),
        "day": now.strftime("%d"),
    }
    merged = {**builtins, **(variables or {})}

    def repl(m: re.Match) -> str:
        return str(merged.get(m.group(1), m.group(0)))

    return _VAR_RE.sub(repl, text)


def register_template_tools(mcp: FastMCP, client: VaultClient, cfg) -> None:
    @mcp.tool(
        description="List available template notes (from the vault's templates folder).",
        annotations={"readOnlyHint": True},
    )
    @traced_tool(mcp_server="obsidian", category="templates")
    async def list_templates(ctx: Context | None = None) -> dict[str, Any]:
        tdir = _find_dir(client, cfg.templates_dir, r"template")
        if tdir is None:
            return {"templates_dir": None, "templates": []}
        names = [
            client.rel(p)
            for p in client.resolve(tdir).glob("*.md")
        ]
        return {"templates_dir": tdir, "templates": sorted(names)}

    @mcp.tool(
        description=(
            "Create a new note from a template, substituting {{title}}, {{date}}, {{time}}, "
            "{{datetime}} and any custom variables. template is a vault-relative path."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="templates")
    async def create_from_template(
        template: str,
        dest: str,
        variables: dict[str, str] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if not client.exists(template):
            return {"status": "error", "error": f"template not found: {template}"}
        if client.exists(dest):
            return {"status": "error", "error": f"destination exists: {dest}"}
        vars_ = dict(variables or {})
        vars_.setdefault("title", client.basename(dest))
        content = _substitute(client.read_note(template), vars_)
        client.write_note(dest, content)
        return {"status": "created", "path": dest, "from_template": template}

    @mcp.tool(
        description="Create or overwrite a template note in the templates folder.",
    )
    @traced_tool(mcp_server="obsidian", category="templates")
    async def upsert_template(
        name: str, content: str, ctx: Context | None = None
    ) -> dict[str, Any]:
        tdir = _find_dir(client, cfg.templates_dir, r"template") or "templates"
        fname = name if name.endswith(".md") else f"{name}.md"
        dest = f"{tdir}/{fname}"
        client.write_note(dest, content)
        return {"status": "saved", "path": dest}

    @mcp.tool(
        description=(
            "Create today's daily note (YYYY-MM-DD.md) in the daily folder, optionally from a "
            "template. Returns the path; no-op if it already exists."
        ),
    )
    @traced_tool(mcp_server="obsidian", category="templates")
    async def create_daily_note(
        template: str | None = None, ctx: Context | None = None
    ) -> dict[str, Any]:
        ddir = _find_dir(client, cfg.daily_dir, r"daily") or "daily"
        today = dt.date.today().strftime("%Y-%m-%d")
        dest = f"{ddir}/{today}.md"
        if client.exists(dest):
            return {"status": "exists", "path": dest}
        if template and client.exists(template):
            content = _substitute(client.read_note(template), {"title": today})
        else:
            content = f"# {today}\n\n"
        client.write_note(dest, content)
        return {"status": "created", "path": dest}
