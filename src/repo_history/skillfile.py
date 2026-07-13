"""Install the bundled Claude Code skill into a ``.claude/skills`` directory."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

SKILL_NAME = "repo-history"


def read_skill_text() -> str:
    """The packaged SKILL.md content."""
    return files("repo_history").joinpath("skill", "SKILL.md").read_text()


def install_skill(base: Path) -> Path:
    """Write the skill under ``<base>/.claude/skills/repo-history/`` and return the path."""
    dest = base / ".claude" / "skills" / SKILL_NAME / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(read_skill_text())
    return dest
