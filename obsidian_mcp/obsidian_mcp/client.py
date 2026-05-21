"""Direct filesystem client for an Obsidian vault.

No API key, no plugin, no HTTP. We treat the vault as a directory tree of
markdown files. This is the simplest possible backend and works for any
Obsidian vault you have on disk.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from shared.tracing import record_upstream


class VaultPathError(ValueError):
    """Raised when a requested path escapes the vault root."""


class VaultClient:
    def __init__(self, vault_path: str | Path):
        self.root = Path(vault_path).expanduser().resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"Vault path does not exist: {self.root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"Vault path is not a directory: {self.root}")

    # --- path safety ---------------------------------------------------------

    def _resolve(self, relative: str) -> Path:
        """Resolve a vault-relative path, refusing anything outside the root."""
        rel = relative.lstrip("/").strip()
        candidate = (self.root / rel).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise VaultPathError(f"Path escapes vault root: {relative}") from exc
        return candidate

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    # --- vault primitives ----------------------------------------------------

    def list_vault(self, directory: str = "") -> list[str]:
        start = time.monotonic()
        target = self._resolve(directory) if directory else self.root
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")
        entries = []
        for child in sorted(target.iterdir()):
            if child.name.startswith("."):
                continue
            suffix = "/" if child.is_dir() else ""
            entries.append(self._rel(child) + suffix)
        record_upstream("vault_fs", int((time.monotonic() - start) * 1000))
        return entries

    def read_note(self, path: str) -> str:
        start = time.monotonic()
        target = self._resolve(path)
        content = target.read_text(encoding="utf-8")
        record_upstream("vault_fs", int((time.monotonic() - start) * 1000))
        return content

    def write_note(self, path: str, content: str) -> None:
        start = time.monotonic()
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        record_upstream("vault_fs", int((time.monotonic() - start) * 1000))

    def append_note(self, path: str, content: str) -> None:
        start = time.monotonic()
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            if target.stat().st_size and not content.startswith("\n"):
                fh.write("\n")
            fh.write(content)
        record_upstream("vault_fs", int((time.monotonic() - start) * 1000))

    def delete_note(self, path: str) -> None:
        start = time.monotonic()
        target = self._resolve(path)
        target.unlink()
        record_upstream("vault_fs", int((time.monotonic() - start) * 1000))

    def search_simple(self, query: str, context_length: int = 100, limit: int = 25
                      ) -> list[dict[str, Any]]:
        """Naive case-insensitive substring search across .md files."""
        start = time.monotonic()
        needle = query.lower()
        results: list[dict[str, Any]] = []
        for md in self.root.rglob("*.md"):
            if any(part.startswith(".") for part in md.relative_to(self.root).parts):
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            lower = text.lower()
            idx = lower.find(needle)
            if idx == -1:
                continue
            half = max(20, context_length // 2)
            snippet = text[max(0, idx - half): idx + len(query) + half]
            results.append({"path": self._rel(md), "match": snippet})
            if len(results) >= limit:
                break
        record_upstream("vault_fs", int((time.monotonic() - start) * 1000))
        return results

    def list_all_notes(self) -> list[str]:
        return [
            self._rel(md)
            for md in self.root.rglob("*.md")
            if not any(p.startswith(".") for p in md.relative_to(self.root).parts)
        ]

    # --- frontmatter helpers (used by tagger sub-agent) ----------------------

    _FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

    def patch_frontmatter(self, path: str, key: str, value: Any) -> None:
        """Set ``key: value`` inside the YAML frontmatter; create block if absent."""
        content = self.read_note(path)
        match = self._FRONTMATTER_RE.match(content)
        if match:
            block = match.group(1)
            line_re = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
            new_line = f"{key}: {value}"
            new_block = line_re.sub(new_line, block) if line_re.search(block) \
                else block.rstrip() + f"\n{new_line}"
            new_content = f"---\n{new_block}\n---\n" + content[match.end():]
        else:
            new_content = f"---\n{key}: {value}\n---\n\n" + content
        self.write_note(path, new_content)

    def close(self) -> None:  # noqa: D401 — for symmetry with async clients
        """No-op (kept so callers can `await client.close()`-style)."""
