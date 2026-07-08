"""Shared, method-agnostic helpers for analyzers.

These are objective facts about the history (is a commit noise? what is a file's
current name after renames?) that any analysis method may want. They are kept
separate from the framework so a method is free to ignore or replace them.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..git import FileChange

# Files whose changes almost never carry engineering intent worth an LLM's time.
_TRIVIAL_BASENAMES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "uv.lock",
        "Cargo.lock",
        "composer.lock",
        "Gemfile.lock",
        "go.sum",
        "flake.lock",
    }
)
_TRIVIAL_SUFFIXES = (".min.js", ".min.css", ".map")


def is_trivial_file(path: str) -> bool:
    """True for generated/lock files whose churn carries no engineering intent."""
    basename = path.rsplit("/", 1)[-1]
    return basename in _TRIVIAL_BASENAMES or path.endswith(_TRIVIAL_SUFFIXES)


def is_trivial(changes: Sequence[FileChange]) -> bool:
    """True if a commit is noise: empty, or only touching generated/lock files."""
    if not changes:
        return True
    return all(is_trivial_file(c.path) for c in changes)


def build_canonical_map(
    renames: Sequence[tuple[str, str]],
) -> dict[str, str]:
    """Map every historical path to its final name, following rename chains.

    ``renames`` is a chronological list of ``(old_path, new_path)`` pairs. If
    ``a.py`` becomes ``b.py`` becomes ``c.py``, both ``a.py`` and ``b.py`` map to
    ``c.py`` so a file's history aggregates under one name.
    """
    direct: dict[str, str] = {}
    for old, new in renames:
        direct[old] = new

    def resolve(path: str) -> str:
        seen: set[str] = set()
        while path in direct and path not in seen:
            seen.add(path)
            path = direct[path]
        return path

    return {old: resolve(old) for old in direct}
