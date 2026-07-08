"""Shared test fixtures.

``fixture_repo`` builds a small but realistic git history in a temp directory:
a root commit, a new abstraction, a rename, an extension, and a *revert* of that
extension, plus an annotated release tag. Dates and identity are pinned so tests
are deterministic.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from repo_history.git import GitRepo

_BASE_TS = 1_700_000_000
_STEP = 3_600


def _git(repo: Path, *args: str, ts: int) -> None:
    date = f"{ts} +0000"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test Dev",
        "GIT_AUTHOR_EMAIL": "dev@example.com",
        "GIT_COMMITTER_NAME": "Test Dev",
        "GIT_COMMITTER_EMAIL": "dev@example.com",
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@dataclass
class FixtureRepo:
    path: Path
    repo: GitRepo
    subjects: list[str]  # commit subjects, oldest first


@pytest.fixture(scope="module")
def fixture_repo(tmp_path_factory: pytest.TempPathFactory) -> FixtureRepo:
    root = tmp_path_factory.mktemp("fixture_repo")
    ts = _BASE_TS

    _git(root, "init", "-b", "main", ts=ts)

    # 1. root commit
    (root / "README.md").write_text("# Demo\n\nhello\n")
    (root / "a.py").write_text("def a():\n    return 1\n")
    _git(root, "add", "-A", ts=ts)
    _git(root, "commit", "-m", "Initial commit", ts=ts)

    # 2. introduce an abstraction
    ts += _STEP
    (root / "helper.py").write_text(
        "class Helper:\n    def run(self):\n        return 'run'\n"
    )
    _git(root, "add", "-A", ts=ts)
    _git(root, "commit", "-m", "Add Helper abstraction", ts=ts)

    # 3. rename a.py -> app.py
    ts += _STEP
    _git(root, "mv", "a.py", "app.py", ts=ts)
    _git(root, "commit", "-m", "Rename a.py to app.py", ts=ts)

    # tag the state after the rename as a release
    _git(root, "tag", "-a", "v1.0", "-m", "release 1.0", ts=ts)

    # 4. extend the abstraction
    ts += _STEP
    (root / "helper.py").write_text(
        "class Helper:\n    def run(self):\n        return 'run'\n"
        "    def extra(self):\n        return 'extra'\n"
    )
    _git(root, "add", "-A", ts=ts)
    _git(root, "commit", "-m", "Extend Helper with extra()", ts=ts)
    extend_sha = GitRepo(root).resolve("HEAD")

    # 5. revert the extension (a genuine "we undid this" episode)
    ts += _STEP
    _git(root, "revert", "--no-edit", extend_sha, ts=ts)

    subjects = [
        "Initial commit",
        "Add Helper abstraction",
        "Rename a.py to app.py",
        "Extend Helper with extra()",
        'Revert "Extend Helper with extra()"',
    ]
    return FixtureRepo(path=root, repo=GitRepo(root), subjects=subjects)
