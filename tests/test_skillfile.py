"""Tests for installing the bundled Claude Code skill."""

from __future__ import annotations

from repo_history.skillfile import install_skill, read_skill_text


def test_skill_text_has_frontmatter() -> None:
    text = read_skill_text()
    assert text.startswith("---")
    assert "name: repo-history" in text


def test_install_skill_writes_file(tmp_path) -> None:
    dest = install_skill(tmp_path)
    assert dest == tmp_path / ".claude" / "skills" / "repo-history" / "SKILL.md"
    assert dest.exists()
    assert "name: repo-history" in dest.read_text()
