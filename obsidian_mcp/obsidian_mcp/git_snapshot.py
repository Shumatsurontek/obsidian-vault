"""Lightweight, isolated vault snapshots backed by git.

Uses a dedicated git directory at ``<vault>/.vault-mcp/snapshots.git`` with the
vault as the work-tree. This never creates a ``.git`` inside the vault and does
not interfere with any git repo the user may already keep there. Plugin and
internal folders are excluded.
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_EXCLUDES = [
    ".obsidian/",
    ".smart-env/",
    ".vault-mcp/",
    ".trash/",
    ".DS_Store",
]

# Consecutive edits within this window share a single pre-edit baseline, so
# `undo_last_pass` reverts the whole batch (an organizer pass, or a burst of
# interactive edits) rather than just the most recent write.
_CHECKPOINT_DEBOUNCE_SECONDS = 90.0


class GitSnapshot:
    def __init__(self, vault_root: Path):
        self.root = Path(vault_root)
        self.git_dir = self.root / ".vault-mcp" / "snapshots.git"
        self._last_checkpoint = 0.0
        # Serialize git index/commit operations. The HTTP server may run tool
        # handlers in threads; a shared work-tree must not see concurrent
        # `git add`/`commit`/`reset`. (Multi-process deploys need 1 worker.)
        self._lock = threading.Lock()

    # --- plumbing ------------------------------------------------------------

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        cmd = [
            "git",
            f"--git-dir={self.git_dir}",
            f"--work-tree={self.root}",
            *args,
        ]
        return subprocess.run(
            cmd, capture_output=True, text=True, check=check, cwd=self.root
        )

    def _ensure_repo(self) -> None:
        if (self.git_dir / "HEAD").exists():
            return
        self.git_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--quiet", f"--separate-git-dir={self.git_dir}", str(self.root)],
            capture_output=True,
            text=True,
            check=True,
            cwd=self.root,
        )
        # `git init <dir>` with --separate-git-dir leaves a `.git` file pointer;
        # remove it so the vault stays pristine. We address the repo via flags.
        dot_git = self.root / ".git"
        if dot_git.exists():
            dot_git.unlink()
        self._git("config", "user.email", "vault-mcp@localhost")
        self._git("config", "user.name", "vault-mcp")
        self._git("config", "commit.gpgsign", "false")
        exclude_file = self.git_dir / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        exclude_file.write_text("\n".join(_EXCLUDES) + "\n", encoding="utf-8")

    # --- public API ----------------------------------------------------------

    def snapshot(self, label: str = "snapshot") -> dict[str, Any]:
        with self._lock:
            self._ensure_repo()
            self._git("add", "-A")
            status = self._git("status", "--porcelain").stdout.strip()
            if not status and self._has_commits():
                return {"status": "unchanged", "sha": self._head()}
            self._git("commit", "--quiet", "--allow-empty", "-m", label)
            self._last_checkpoint = time.monotonic()
            return {"status": "snapshot", "sha": self._head(), "label": label}

    def checkpoint(self, label: str = "auto: pre-edit baseline") -> dict[str, Any]:
        """Capture the current (pre-edit) state as a restore point before a write.

        Called automatically by the vault client ahead of every mutation. It is
        debounced (see ``_CHECKPOINT_DEBOUNCE_SECONDS``): the first write of a
        batch commits a baseline, and rapid follow-up writes reuse it so a single
        ``undo_last_pass`` reverts the entire batch. The very first write to a
        fresh repo always commits, so undo is never left with nothing to restore.
        """
        with self._lock:
            self._ensure_repo()
            now = time.monotonic()
            first_ever = not self._has_commits()
            if not first_ever and (now - self._last_checkpoint) < _CHECKPOINT_DEBOUNCE_SECONDS:
                return {"status": "debounced"}
            self._git("add", "-A")
            dirty = bool(self._git("status", "--porcelain").stdout.strip())
            if not dirty and not first_ever:
                self._last_checkpoint = now
                return {"status": "unchanged", "sha": self._head()}
            self._git("commit", "--quiet", "--allow-empty", "-m", label)
            self._last_checkpoint = now
            return {"status": "checkpoint", "sha": self._head(), "label": label}

    def list_snapshots(self, limit: int = 20) -> list[dict[str, str]]:
        if not self._has_commits():
            return []
        out = self._git(
            "log", f"-{limit}", "--pretty=format:%H%x1f%cI%x1f%s"
        ).stdout.strip()
        rows = []
        for line in out.splitlines():
            sha, when, label = line.split("\x1f")
            rows.append({"sha": sha, "when": when, "label": label})
        return rows

    def restore(self, sha: str | None = None) -> dict[str, Any]:
        """Restore the vault work-tree to a snapshot (default: latest)."""
        with self._lock:
            if not self._has_commits():
                return {"status": "error", "error": "no snapshots exist yet"}
            target = sha or self._head()
            self._git("reset", "--hard", "--quiet", target)
            # Drop files created after the snapshot (respecting excludes).
            self._git("clean", "-fdq")
            return {"status": "restored", "sha": target}

    # --- helpers -------------------------------------------------------------

    def _has_commits(self) -> bool:
        return self._git("rev-parse", "--verify", "HEAD", check=False).returncode == 0

    def _head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()
