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
            # an inferred decision, to check it sorts *after* the observed one below
            Decision(statement="Prefer typer for the CLI", why="", basis="inferred"),
            Decision(
                statement="Adopt a src layout",
                why="cleaner packaging",
                basis="observed",
                evidence=[episodes[0].id],
            ),
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
            Landmine(
                lesson="Do not reintroduce Helper.extra()",
                detail="It was reverted.",
                basis="observed",
                evidence=[revert_ep.id],
            )
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
        "GUARDRAILS.md",  # flagship, at the root
        "DECISIONS.md",
        "LANDMINES.md",
        "onboarding/TIMELINE.md",  # narrative demoted to a subdirectory
        "onboarding/ARCHITECTURE.md",
        "onboarding/HOTSPOTS.md",
        "timeline.json",  # json mirrors stay flat at the root
        "decisions.json",
        "landmines.json",
        "hotspots.json",
        "index.json",
    ]:
        assert (out / name).exists(), f"missing {name}"

    assert result.decisions == 2
    assert result.landmines == 1


def test_guardrails_lead_with_evidence_and_trust(fixture_repo: FixtureRepo, tmp_path) -> None:
    out = _prepare(fixture_repo, tmp_path)
    build_artifacts(out)
    guardrails = (out / "GUARDRAILS.md").read_text()

    # both a landmine and a decision surface in the flagship file
    assert "Do not reintroduce Helper.extra()" in guardrails
    assert "Adopt a src layout" in guardrails
    # trust is graded and evidence-linked
    assert "[observed]" in guardrails and "[inferred]" in guardrails
    # observed decision sorts before the inferred one
    assert guardrails.index("Adopt a src layout") < guardrails.index("Prefer typer for the CLI")


def test_build_content_reflects_analyses(fixture_repo: FixtureRepo, tmp_path) -> None:
    out = _prepare(fixture_repo, tmp_path)
    build_artifacts(out)

    assert "Adopt a src layout" in (out / "DECISIONS.md").read_text()
    assert "Do not reintroduce Helper.extra()" in (out / "LANDMINES.md").read_text()
    assert "Bootstrapped the project." in (out / "onboarding" / "TIMELINE.md").read_text()

    decisions = json.loads((out / "decisions.json").read_text())
    observed = next(d for d in decisions if d["statement"] == "Adopt a src layout")
    assert observed["basis"] == "observed"  # trust signal survives into JSON
    assert observed["episode"]


def test_build_hotspots_without_analyses(fixture_repo: FixtureRepo, tmp_path) -> None:
    # Hotspots come from mechanical analysis and must render with no LLM output.
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialize(fixture_repo.repo, result, out, ref="main")

    build_result = build_artifacts(out)
    assert build_result.episodes == 0
    assert "helper.py" in (out / "onboarding" / "HOTSPOTS.md").read_text()
    assert "No guardrails yet" in (out / "GUARDRAILS.md").read_text()
