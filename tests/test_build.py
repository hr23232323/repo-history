"""Tests for rendering .repo-memory artifacts from episode analyses."""

from __future__ import annotations

import json

import pytest
from conftest import FixtureRepo

from repo_history.analysis import run_analysis
from repo_history.build import BuildError, build_artifacts
from repo_history.models import Decision, EpisodeAnalysis, Landmine
from repo_history.work import materialize


def _prepare(fixture_repo: FixtureRepo, tmp_path):
    """Run plan + write two hand-authored analyses, as the skill would."""
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialize(fixture_repo.repo, result, out, ref="main")

    analyses_dir = out / ".work" / "analyses"
    analyses_dir.mkdir(parents=True)
    episodes = result.episodes

    first = EpisodeAnalysis(
        id=episodes[0].id,
        title=episodes[0].title,
        summary="Bootstrapped the project.",
        decisions=[
            Decision(statement="Adopt a src layout", why="cleaner packaging", evidence=[episodes[0].id])
        ],
    )
    revert_ep = next(e for e in episodes if e.kind == "revert")
    reverted = EpisodeAnalysis(
        id=revert_ep.id,
        title=revert_ep.title,
        summary="Undid the Helper.extra() method.",
        kind="revert",
        architecture_note="Helper kept minimal.",
        landmines=[
            Landmine(lesson="Do not reintroduce Helper.extra()", detail="It was reverted.", evidence=[revert_ep.id])
        ],
    )
    (analyses_dir / f"{first.id}.json").write_text(first.model_dump_json())
    (analyses_dir / f"{reverted.id}.json").write_text(reverted.model_dump_json())
    return out


def test_build_requires_manifest(tmp_path) -> None:
    with pytest.raises(BuildError):
        build_artifacts(tmp_path / ".repo-memory")


def test_build_reports_corrupt_manifest(fixture_repo: FixtureRepo, tmp_path) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialize(fixture_repo.repo, result, out, ref="main")
    (out / ".work" / "manifest.json").write_text("{ not valid json")
    with pytest.raises(BuildError, match="corrupt"):
        build_artifacts(out)


def test_build_writes_all_artifacts(fixture_repo: FixtureRepo, tmp_path) -> None:
    out = _prepare(fixture_repo, tmp_path)
    result = build_artifacts(out)

    for name in [
        "TIMELINE.md",
        "DECISIONS.md",
        "LANDMINES.md",
        "ARCHITECTURE.md",
        "HOTSPOTS.md",
        "timeline.json",
        "decisions.json",
        "landmines.json",
        "hotspots.json",
        "index.json",
    ]:
        assert (out / name).exists(), f"missing {name}"

    assert result.decisions == 1
    assert result.landmines == 1


def test_build_content_reflects_analyses(fixture_repo: FixtureRepo, tmp_path) -> None:
    out = _prepare(fixture_repo, tmp_path)
    build_artifacts(out)

    assert "Adopt a src layout" in (out / "DECISIONS.md").read_text()
    assert "Do not reintroduce Helper.extra()" in (out / "LANDMINES.md").read_text()
    assert "Bootstrapped the project." in (out / "TIMELINE.md").read_text()

    decisions = json.loads((out / "decisions.json").read_text())
    assert decisions[0]["statement"] == "Adopt a src layout"
    assert decisions[0]["episode"]


def test_build_hotspots_without_analyses(fixture_repo: FixtureRepo, tmp_path) -> None:
    # Hotspots come from mechanical analysis and must render with no LLM output.
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialize(fixture_repo.repo, result, out, ref="main")

    build_result = build_artifacts(out)
    assert build_result.episodes == 0
    hotspots_md = (out / "HOTSPOTS.md").read_text()
    assert "helper.py" in hotspots_md
    assert "No episode analyses yet" in (out / "TIMELINE.md").read_text()
