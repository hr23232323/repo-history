"""Incremental state: what has been analyzed, and what is new since.

``build`` records the head it analyzed in ``index.json``. Comparing that head to
the branch's current tip tells us exactly which commits a re-run needs to cover,
so the expensive LLM pass only ever sees new history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .git import GitError, GitRepo


@dataclass
class Status:
    has_memory: bool
    method: str | None = None
    ref: str | None = None
    head: str | None = None
    built_at: str | None = None
    counts: dict = field(default_factory=dict)
    new_commits: int = 0
    head_missing: bool = False  # recorded head is not in this repo (rebased/force-pushed?)


def read_status(repo: GitRepo, out_dir: Path, ref: str | None = None) -> Status:
    """Compare the last-built head against the current tip of ``ref``."""
    index_path = out_dir / "index.json"
    if not index_path.exists():
        return Status(has_memory=False)

    index = json.loads(index_path.read_text())
    head = index.get("head")
    target_ref = ref or index.get("ref") or "HEAD"
    status = Status(
        has_memory=True,
        method=index.get("method"),
        ref=target_ref,
        head=head,
        built_at=index.get("built_at"),
        counts=index.get("counts", {}),
    )
    if not head:
        return status

    try:
        repo.resolve(head)
    except GitError:
        status.head_missing = True
        return status

    status.new_commits = len(repo.commits(target_ref, since=head))
    return status
