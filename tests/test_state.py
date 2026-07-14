"""Tests for incremental state tracking."""

from __future__ import annotations

import subprocess

from conftest import FixtureRepo, _git

from repo_history.analysis import run_analysis
from repo_history.build import build_artifacts
from repo_history.git import GitRepo
from repo_history.state import read_status
from repo_history.work import materialize


def _plan_and_build(repo: GitRepo, out, ref: str = "main"):
    result = run_analysis(repo, ref, method="mechanical")
    materialize(repo, result, out, ref=ref)
    return build_artifacts(out)


def test_status_without_memory(fixture_repo: FixtureRepo, tmp_path) -> None:
    status = read_status(fixture_repo.repo, tmp_path / ".repo-memory")
    assert status.has_memory is False
    assert status.new_commits == 0


def test_status_is_up_to_date_after_build(fixture_repo: FixtureRepo, tmp_path) -> None:
    out = tmp_path / ".repo-memory"
    _plan_and_build(fixture_repo.repo, out)

    status = read_status(fixture_repo.repo, out)
    assert status.has_memory is True
    assert status.method == "mechanical"
    assert status.ref == "main"
    assert status.head == fixture_repo.repo.resolve("main")
    assert status.new_commits == 0
    assert status.head_missing is False


def test_status_detects_new_commits(tmp_path) -> None:
    # A throwaway clone so we can add a commit without disturbing the shared fixture.
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-b", "main", ts=1_700_000_000)
    (work / "a.py").write_text("x = 1\n")
    _git(work, "add", "-A", ts=1_700_000_000)
    _git(work, "commit", "-m", "first", ts=1_700_000_000)

    repo = GitRepo(work)
    out = tmp_path / ".repo-memory"
    _plan_and_build(repo, out)
    assert read_status(repo, out).new_commits == 0

    (work / "a.py").write_text("x = 2\n")
    _git(work, "add", "-A", ts=1_700_003_600)
    _git(work, "commit", "-m", "second", ts=1_700_003_600)

    status = read_status(repo, out)
    assert status.new_commits == 1

    # An incremental plan sees only the new commit.
    incremental = run_analysis(repo, "main", method="mechanical", since=status.head)
    assert incremental.summary["total_commits"] == 1
    assert incremental.episodes[0].title == "second"


def test_status_flags_missing_head(fixture_repo: FixtureRepo, tmp_path) -> None:
    out = tmp_path / ".repo-memory"
    _plan_and_build(fixture_repo.repo, out)

    index = out / "index.json"
    index.write_text(index.read_text().replace(fixture_repo.repo.resolve("main"), "0" * 40))

    status = read_status(fixture_repo.repo, out)
    assert status.head_missing is True
