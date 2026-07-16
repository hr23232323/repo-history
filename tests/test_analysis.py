"""Tests for the pluggable analysis framework and the mechanical method."""

from __future__ import annotations

import json

import pytest
from conftest import FixtureRepo, _git

from repo_history.analysis import (
    AnalysisContext,
    CommitStats,
    available,
    get_analyzer,
    run_analysis,
)
from repo_history.analysis.mechanical import (
    MechanicalAnalyzer,
    compute_coupling,
    detect_reverts,
)
from repo_history.analysis.util import is_trivial
from repo_history.git import Commit, FileChange, GitRepo


def _stats(sha: str, paths: list[str], *, subject: str = "c", body: str = "") -> CommitStats:
    commit = Commit(
        sha=sha,
        short_sha=sha[:7],
        author_name="a",
        author_email="a@b",
        timestamp=0,
        parents=("parent",),
        subject=subject,
        body=body,
    )
    changes = tuple(FileChange(path=p, added=1, deleted=0) for p in paths)
    return CommitStats(commit=commit, changes=changes, trivial=False)


def _ctx(stats: list[CommitStats]) -> AnalysisContext:
    return AnalysisContext(repo=None, ref="main", stats=stats, canonical={}, tags=[])  # type: ignore[arg-type]


# -- framework -------------------------------------------------------------


def test_registry_exposes_mechanical() -> None:
    keys = [k for k, _title, _desc in available()]
    assert "mechanical" in keys
    assert isinstance(get_analyzer("mechanical"), MechanicalAnalyzer)


def test_unknown_method_raises() -> None:
    with pytest.raises(KeyError):
        get_analyzer("does-not-exist")


def test_result_is_json_serializable(fixture_repo: FixtureRepo) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    dumped = json.dumps(result.to_dict())  # must not raise on dataclasses
    reloaded = json.loads(dumped)
    assert reloaded["method"] == "mechanical"
    assert "episodes" in reloaded and "sections" in reloaded


# -- mechanical method on the fixture -------------------------------------


def test_mechanical_summary(fixture_repo: FixtureRepo) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    summary = result.summary
    assert summary["total_commits"] == 5
    assert summary["significant_commits"] == 5
    assert summary["merge_commits"] == 0
    assert summary["reverts"] == 1


def test_mechanical_detects_the_revert(fixture_repo: FixtureRepo) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    reverts = result.sections["reverts"]
    assert len(reverts) == 1
    assert reverts[0].reverts_subject == "Extend Helper with extra()"
    assert reverts[0].reverts_sha is not None  # git records the target sha in the body


def test_mechanical_hotspot_follows_renames(fixture_repo: FixtureRepo) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    hotspots = {h.path: h for h in result.sections["hotspots"]}
    # a.py was renamed to app.py; its history aggregates under the new name.
    assert "a.py" not in hotspots
    assert hotspots["app.py"].commits == 2
    # helper.py is touched by add, extend, and revert -> the top hotspot.
    assert result.sections["hotspots"][0].path == "helper.py"
    assert hotspots["helper.py"].commits == 3


def test_mechanical_isolates_revert_episode(fixture_repo: FixtureRepo) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    revert_eps = [e for e in result.episodes if e.kind == "revert"]
    assert len(revert_eps) == 1
    assert "helper.py" in revert_eps[0].paths
    assert len(revert_eps[0].commit_shas) == 1


# -- isolated unit tests ---------------------------------------------------


def test_episode_grouping_keeps_tagged_commit_with_its_release(tmp_path) -> None:
    # The commit a tag points at should group with its release predecessors, not
    # with post-release work. This distinguishes bisect_left from bisect_right.
    d = tmp_path / "rel"
    d.mkdir()
    ts = 1_700_000_000
    _git(d, "init", "-b", "main", ts=ts)
    for i, content in enumerate(["1\n", "2\n"]):
        (d / "a.py").write_text(content)
        _git(d, "add", "-A", ts=ts + i * 3600)
        _git(d, "commit", "-m", f"c{i + 1}", ts=ts + i * 3600)
    _git(d, "tag", "-a", "v1", "-m", "release", ts=ts + 3600)  # tag points at c2
    (d / "a.py").write_text("3\n")
    _git(d, "add", "-A", ts=ts + 7200)
    _git(d, "commit", "-m", "c3", ts=ts + 7200)

    repo = GitRepo(d)
    sha = {c.subject: c.sha for c in repo.commits("main")}
    result = run_analysis(repo, "main", method="mechanical")
    ep_of = {s: e for e in result.episodes for s in e.commit_shas}

    assert ep_of[sha["c1"]].id == ep_of[sha["c2"]].id  # c2 (tagged) stays with c1
    assert ep_of[sha["c3"]].id != ep_of[sha["c1"]].id  # c3 (post-release) splits off


def test_coupling_counts_cochanges() -> None:
    stats = [
        _stats("1", ["x.py", "y.py"]),
        _stats("2", ["x.py", "y.py"]),
        _stats("3", ["x.py", "z.py"]),
    ]
    pairs = compute_coupling(_ctx(stats), stats, min_shared=2)
    assert len(pairs) == 1
    pair = pairs[0]
    assert (pair.a, pair.b) == ("x.py", "y.py")
    assert pair.co_changes == 2
    assert pair.confidence == 1.0  # y.py always co-changes with x.py


def test_detect_reverts_by_subject_only() -> None:
    stats = [_stats("1", ["a.py"], subject='Revert "Add thing"', body="")]
    reverts = detect_reverts(stats)
    assert len(reverts) == 1
    assert reverts[0].reverts_subject == "Add thing"
    assert reverts[0].reverts_sha is None


@pytest.mark.parametrize(
    "paths,expected",
    [
        ([], True),
        (["uv.lock"], True),
        (["a/b/package-lock.json"], True),
        (["dist/app.min.js"], True),
        (["src/main.py"], False),
        (["uv.lock", "src/main.py"], False),  # mixed -> not trivial
    ],
)
def test_is_trivial(paths: list[str], expected: bool) -> None:
    changes = [FileChange(path=p, added=1, deleted=0) for p in paths]
    assert is_trivial(changes) is expected
