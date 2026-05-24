"""YAML frontmatter + inline #tag parsing helpers."""

from __future__ import annotations

import re
from typing import Any

import yaml

_FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
# Inline #tags: word chars, hyphen, slash. Skips markdown headings (# + space).
_INLINE_TAG_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9_][A-Za-z0-9_\-/]*)")


def parse(content: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body). Empty dict if no/invalid frontmatter."""
    match = _FM_RE.match(content)
    if not match:
        return {}, content
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}, content
    if not isinstance(data, dict):
        return {}, content
    return data, content[match.end():]


def dump(frontmatter: dict[str, Any], body: str) -> str:
    if not frontmatter:
        return body
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_text}\n---\n{body if body.startswith(chr(10)) else chr(10) + body}"


def normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in re.split(r"[,\s]+", value) if t.strip()]
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    return []


def note_tags(content: str) -> list[str]:
    """All tags for a note: frontmatter `tags` + inline #tags, deduped."""
    fm, body = parse(content)
    tags = set(normalize_tags(fm.get("tags")))
    tags.update(m.group(1) for m in _INLINE_TAG_RE.finditer(body))
    return sorted(tags)


def frontmatter_tags(content: str) -> list[str]:
    fm, _ = parse(content)
    return normalize_tags(fm.get("tags"))
