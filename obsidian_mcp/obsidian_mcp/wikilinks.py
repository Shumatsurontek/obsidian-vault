"""Shared wiki-link parsing/rewriting helpers."""

from __future__ import annotations

import re

# [[target]] | [[target|alias]] | [[target#heading]] | [[target#heading|alias]]
WIKILINK = re.compile(r"\[\[([^\]\|#]+?)((?:#[^\]\|]+)?)(\|[^\]]+)?\]\]")


def extract_targets(markdown: str) -> list[str]:
    """Return the link targets (without heading/alias) referenced in the text."""
    return [m.group(1).strip() for m in WIKILINK.finditer(markdown)]


def rewrite_target(markdown: str, old_target: str, new_target: str) -> tuple[str, int]:
    """Rewrite every [[old_target...]] to [[new_target...]], keeping heading/alias.

    Matching is on the link target (basename or path). Returns (new_text, count).
    """
    count = 0
    old_norm = old_target.strip()

    def repl(m: re.Match) -> str:
        nonlocal count
        target = m.group(1).strip()
        if target != old_norm:
            return m.group(0)
        count += 1
        heading = m.group(2) or ""
        alias = m.group(3) or ""
        return f"[[{new_target}{heading}{alias}]]"

    return WIKILINK.sub(repl, markdown), count
