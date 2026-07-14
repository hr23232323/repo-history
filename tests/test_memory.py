"""Tests for the read-only .repo-memory query layer."""

from __future__ import annotations

import pytest
from conftest import FixtureRepo

from repo_history.analysis import run_analysis
from repo_history.build import build_artifacts
from repo_history.memory import RepoMemory
from repo_history.models import Decision, EpisodeAnalysis, Landmine
from repo_history.work import materialize


@pytest.fixture
def memory(fixture_repo: FixtureRepo, tmp_path) -> RepoMemory:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialize(fixture_repo.repo, result, out, ref="main")

    analyses_dir = out / ".work" / "analyses"
    analyses_dir.mkdir(parents=True)
    for ep in result.episodes:
        if ep.kind == "revert":
            analysis = EpisodeAnalysis(
                id=ep.id,
                title=ep.title,
                summary="Undid Helper.extra().",
                kind="revert",
                landmines=[Landmine(lesson="Do not reintroduce Helper.extra()", detail="reverted")],
            )
        else:
            analysis = EpisodeAnalysis(
                id=ep.id,
                title=ep.title,
                summary=f"Worked on {', '.join(ep.paths) or 'setup'}.",
                decisions=[Decision(statement=f"Touch {p}", why="needed") for p in ep.paths[:1]],
            )
        (analyses_dir / f"{ep.id}.json").write_text(analysis.model_dump_json())

    build_artifacts(out)
    return RepoMemory(out)


def test_has_memory(memory: RepoMemory) -> None:
    assert memory.has_memory is True
    assert memory.timeline()
    assert memory.decisions()


def test_decisions_topic_filter(memory: RepoMemory) -> None:
    all_decisions = memory.decisions()
    helper = memory.decisions(topic="helper.py")
    assert 0 < len(helper) <= len(all_decisions)
    assert all("helper.py" in d["statement"].lower() or "helper.py" in d["why"].lower() for d in helper)


def test_why_is_this_finds_episodes_for_a_file(memory: RepoMemory) -> None:
    result = memory.why("helper.py")
    assert result["path"] == "helper.py"
    assert result["episodes"], "helper.py should map to at least one episode"
    # helper.py is where the revert happened, so its landmine should surface
    lessons = [m["lesson"] for m in result["landmines"]]
    assert any("Helper.extra()" in x for x in lessons)


def test_why_is_this_unknown_file_is_empty(memory: RepoMemory) -> None:
    result = memory.why("does/not/exist.py")
    assert result["episodes"] == []
    assert result["decisions"] == []


def test_check_before_you_do_matches_landmine(memory: RepoMemory) -> None:
    hits = memory.check_before_you_do("I want to add an extra method to Helper")
    assert any("Helper.extra()" in m["lesson"] for m in hits)


def test_check_before_you_do_no_match(memory: RepoMemory) -> None:
    assert memory.check_before_you_do("completely unrelated wombat telemetry") == []
