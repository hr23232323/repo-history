"""Tests for the read-only git access layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import FixtureRepo, _git

from repo_history.git import GitError, GitRepo, _parse_numstat_path


def test_not_a_git_repo(tmp_path: Path) -> None:
    with pytest.raises(GitError):
        GitRepo(tmp_path)


def test_commits_survive_separator_bytes_in_body(tmp_path: Path) -> None:
    # A commit body containing the field/record separator bytes must not split
    # into a spurious record or truncate the body (untrusted-repo posture).
    repo_dir = tmp_path / "sep"
    repo_dir.mkdir()
    ts = 1_700_000_000
    _git(repo_dir, "init", "-b", "main", ts=ts)
    (repo_dir / "f.txt").write_text("x\n")
    _git(repo_dir, "add", "-A", ts=ts)
    _git(repo_dir, "commit", "-m", "subject line", "-m", "before\x1emid\x1fafter", ts=ts)

    commits = GitRepo(repo_dir).commits("main")
    assert len(commits) == 1
    assert commits[0].subject == "subject line"
    assert "before" in commits[0].body and "after" in commits[0].body


def test_commits_are_chronological(fixture_repo: FixtureRepo) -> None:
    commits = fixture_repo.repo.commits("main")
    assert [c.subject for c in commits] == fixture_repo.subjects
    # oldest first => strictly non-decreasing author timestamps
    times = [c.timestamp for c in commits]
    assert times == sorted(times)


def test_root_and_merge_flags(fixture_repo: FixtureRepo) -> None:
    commits = fixture_repo.repo.commits("main")
    assert commits[0].is_root
    assert commits[0].parents == ()
    assert all(not c.is_merge for c in commits)  # linear history
    assert all(len(c.parents) == 1 for c in commits[1:])


def test_max_count_and_since(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    all_commits = repo.commits("main")
    # since is an exclusive lower bound: only commits after the 3rd remain.
    third = all_commits[2].sha
    tail = repo.commits("main", since=third)
    assert [c.subject for c in tail] == fixture_repo.subjects[3:]


def test_file_changes_detects_rename(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    rename_commit = next(
        c for c in repo.commits("main") if c.subject.startswith("Rename")
    )
    changes = repo.file_changes(rename_commit.sha)
    renamed = [c for c in changes if c.renamed]
    assert len(renamed) == 1
    assert renamed[0].path == "app.py"
    assert renamed[0].old_path == "a.py"


def test_file_changes_line_churn(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    root = repo.commits("main")[0]
    changes = {c.path: c for c in repo.file_changes(root.sha)}
    assert set(changes) == {"README.md", "a.py"}
    # root commit only adds lines
    assert all(c.deleted == 0 and c.added > 0 for c in changes.values())


def test_raw_diff_contains_change(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    extend = next(
        c for c in repo.commits("main") if c.subject.startswith("Extend")
    )
    diff = repo.raw_diff(extend.sha)
    assert "def extra" in diff
    assert "helper.py" in diff


def test_raw_diff_byte_cap_truncates(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    sha = repo.resolve("main")
    full = repo.raw_diff(sha)
    capped = repo.raw_diff(sha, max_chars=20)
    assert "diff truncated" in capped
    assert len(capped) < len(full)


def test_tags_resolves_annotated(fixture_repo: FixtureRepo) -> None:
    tags = fixture_repo.repo.tags()
    assert [t.name for t in tags] == ["v1.0"]
    # annotated tag must resolve to the underlying commit sha
    commit_at_tag = next(
        c for c in fixture_repo.repo.commits("main") if c.subject.startswith("Rename")
    )
    assert tags[0].sha == commit_at_tag.sha


def test_rejects_option_like_ref(fixture_repo: FixtureRepo) -> None:
    for bad in ["--output=/tmp/x", "-x", "--upload-pack=evil", "ref with space"]:
        with pytest.raises(GitError):
            fixture_repo.repo.commits(bad)
        with pytest.raises(GitError):
            fixture_repo.repo.resolve(bad)


def test_arg_injection_writes_no_file(fixture_repo: FixtureRepo, tmp_path) -> None:
    target = tmp_path / "pwned.txt"
    with pytest.raises(GitError):
        fixture_repo.repo.commits(f"--output={target}")
    assert not target.exists()  # the whole point: no arbitrary file write


def test_since_is_also_guarded(fixture_repo: FixtureRepo, tmp_path) -> None:
    target = tmp_path / "pwned2.txt"
    with pytest.raises(GitError):
        fixture_repo.repo.commits("main", since=f"--output={target}")
    assert not target.exists()


@pytest.mark.parametrize(
    "raw,expected_new,expected_old",
    [
        ("src/app.py", "src/app.py", None),
        ("old.py => new.py", "new.py", "old.py"),
        ("src/{old => new}/file.py", "src/new/file.py", "src/old/file.py"),
        ("src/{ => sub}/file.py", "src/sub/file.py", "src/file.py"),
    ],
)
def test_parse_numstat_path(raw: str, expected_new: str, expected_old: str | None) -> None:
    new, old = _parse_numstat_path(raw)
    assert new == expected_new
    assert old == expected_old
