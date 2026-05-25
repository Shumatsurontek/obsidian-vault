"""Tests for Related-section insertion and link removal helpers."""

from __future__ import annotations

from obsidian_mcp.client import VaultClient
from obsidian_mcp.tools.links import insert_related_link, remove_link

key = VaultClient.link_key


def test_appends_after_last_bullet_in_existing_related():
    content = "# Note\n\nBody.\n\n---\n\n## Related\n\n- [[A]]\n- [[B]]\n"
    out = insert_related_link(content, "[[C]]")
    assert out == "# Note\n\nBody.\n\n---\n\n## Related\n\n- [[A]]\n- [[B]]\n- [[C]]\n"


def test_reuses_numbered_related_notes_heading():
    # The real ONBOARDING.md bug: a "## 14. Related notes" heading was not
    # recognized, so a duplicate "## Related" got appended.
    content = "# X\n\n## 14. Related notes\n\n- [[A]]\n"
    out = insert_related_link(content, "[[B]]")
    assert "## 14. Related notes\n\n- [[A]]\n- [[B]]\n" in out
    assert out.count("## Related") == 0


def test_creates_section_when_absent():
    content = "# X\n\nBody.\n"
    out = insert_related_link(content, "[[A]]")
    assert out == "# X\n\nBody.\n\n## Related\n\n- [[A]]\n"


def test_empty_related_section_gets_bullet():
    content = "# X\n\n## Related\n\n## Other\n\ntext\n"
    out = insert_related_link(content, "[[A]]")
    assert "## Related\n\n- [[A]]\n" in out


def test_no_stray_blank_line_between_bullets():
    # The original re.sub inserted the link flush under the header, leaving a
    # blank line before the existing bullets. Bullets must stay contiguous.
    content = "## Related\n\n- [[A]]\n"
    out = insert_related_link(content, "[[B]]")
    assert out == "## Related\n\n- [[A]]\n- [[B]]\n"
    assert "\n\n- [[B]]" not in out


def test_remove_link_drops_bullet_and_counts():
    content = "## Related\n\n- [[A]]\n- [[B]]\n"
    out, n = remove_link(content, "a", title_of=key)  # case-insensitive
    assert n == 1
    assert "[[A]]" not in out
    assert "[[B]]" in out
    assert "- \n" not in out
    assert "-\n" not in out


def test_remove_link_handles_alias_and_heading():
    content = "See [[Topic|the topic]] and [[Topic#Section]].\n"
    out, n = remove_link(content, "topic", title_of=key)
    assert n == 2
    assert "[[" not in out


def test_remove_link_not_found_is_noop():
    content = "## Related\n\n- [[A]]\n"
    out, n = remove_link(content, "zzz", title_of=key)
    assert n == 0
    assert out == content
