"""Tests for the auto-snapshot safety net wired into VaultClient mutations."""

from __future__ import annotations

from obsidian_mcp.client import VaultClient
from obsidian_mcp.git_snapshot import _CHECKPOINT_DEBOUNCE_SECONDS


def _vault(tmp_path):
    (tmp_path / "foo.md").write_text("v1\n", encoding="utf-8")
    return VaultClient(tmp_path)


def test_first_write_creates_baseline_and_undo_restores(tmp_path):
    client = _vault(tmp_path)
    client.write_note("foo.md", "v2\n")
    assert (tmp_path / "foo.md").read_text() == "v2\n"
    assert len(client.snapshot.list_snapshots()) == 1
    client.snapshot.restore()
    assert (tmp_path / "foo.md").read_text() == "v1\n"


def test_debounced_batch_undone_as_one(tmp_path):
    client = _vault(tmp_path)
    client.write_note("foo.md", "v2\n")   # baseline = v1
    client.write_note("foo.md", "v3\n")   # debounced
    client.write_note("bar.md", "new\n")  # debounced
    assert len(client.snapshot.list_snapshots()) == 1  # one baseline for the batch
    client.snapshot.restore()
    assert (tmp_path / "foo.md").read_text() == "v1\n"
    assert not (tmp_path / "bar.md").exists()  # clean removes the new file too


def test_new_batch_after_debounce_window(tmp_path):
    client = _vault(tmp_path)
    client.write_note("foo.md", "v2\n")
    # simulate the debounce window elapsing between batches
    client.snapshot._last_checkpoint -= _CHECKPOINT_DEBOUNCE_SECONDS + 1
    client.write_note("foo.md", "v3\n")  # commits v2 as a fresh baseline
    assert len(client.snapshot.list_snapshots()) == 2
    client.snapshot.restore()            # undo only the latest batch
    assert (tmp_path / "foo.md").read_text() == "v2\n"


def test_delete_is_recoverable(tmp_path):
    client = _vault(tmp_path)
    client.delete_note("foo.md")
    assert not (tmp_path / "foo.md").exists()
    client.snapshot.restore()
    assert (tmp_path / "foo.md").read_text() == "v1\n"


def test_auto_snapshot_can_be_disabled(tmp_path):
    (tmp_path / "foo.md").write_text("v1\n", encoding="utf-8")
    client = VaultClient(tmp_path, auto_snapshot=False)
    assert client.snapshot is None
    client.write_note("foo.md", "v2\n")  # must not raise
    assert (tmp_path / "foo.md").read_text() == "v2\n"
