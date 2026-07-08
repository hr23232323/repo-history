"""Materialize an analysis result into an on-disk work manifest.

This is the hand-off from the deterministic engine to the LLM step. For each
episode it writes a self-contained Markdown bundle (commit messages + condensed,
secret-scrubbed diffs) that a single subagent can read and summarize. The format
is method-agnostic: whatever produced the episodes, the bundles look the same.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .analysis import AnalysisResult, Episode
from .git import GitRepo
from .security import scrub

# Keep bundles readable and cheap: truncate runaway diffs.
_MAX_FILE_LINES = 200
_MAX_TOTAL_LINES = 1500

WORK_DIRNAME = ".work"


@dataclass
class Materialized:
    work_dir: Path
    episode_count: int
    redactions: int


def condense_diff(
    diff: str, *, max_file_lines: int = _MAX_FILE_LINES, max_total_lines: int = _MAX_TOTAL_LINES
) -> str:
    """Trim a unified diff: cap lines per file and overall, with clear markers."""
    if not diff.strip():
        return diff
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git ") and current:
            chunks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append(current)

    out: list[str] = []
    total = 0
    for chunk in chunks:
        if len(chunk) > max_file_lines:
            chunk = chunk[:max_file_lines] + [
                f"... [{len(chunk) - max_file_lines} more lines truncated]"
            ]
        for line in chunk:
            if total >= max_total_lines:
                out.append(f"... [diff truncated at {max_total_lines} lines]")
                return "\n".join(out)
            out.append(line)
            total += 1
    return "\n".join(out)


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def render_bundle(repo: GitRepo, episode: Episode) -> tuple[str, int]:
    """Return ``(markdown, redaction_count)`` for one episode."""
    lines = [
        f"# {episode.id}: {episode.title}",
        "",
        f"- **kind**: {episode.kind}",
        f"- **rationale**: {episode.rationale}",
        f"- **files**: {', '.join(episode.paths) or '(none)'}",
        "",
        "## Commits",
        "",
    ]
    redactions = 0
    for sha in episode.commit_shas:
        commit = repo.commit(sha)
        body, r1 = scrub(commit.body)
        diff, r2 = scrub(condense_diff(repo.raw_diff(sha)))
        redactions += r1 + r2
        lines.append(f"### {commit.short_sha} — {commit.subject}")
        lines.append(f"_{commit.author_name} · {_iso(commit.timestamp)}_")
        lines.append("")
        if body.strip():
            lines += [body.strip(), ""]
        lines += ["```diff", diff, "```", ""]
    return "\n".join(lines), redactions


def materialize(
    repo: GitRepo, result: AnalysisResult, out_dir: Path, *, ref: str
) -> Materialized:
    """Write the work manifest, per-episode bundles, and full analysis to disk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # The work dir is intermediate scaffolding; keep it out of the user's commits.
    (out_dir / ".gitignore").write_text(f"{WORK_DIRNAME}/\n")

    work_dir = out_dir / WORK_DIRNAME
    episodes_dir = work_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    redactions = 0
    index: list[dict] = []
    for episode in result.episodes:
        bundle, r = render_bundle(repo, episode)
        redactions += r
        bundle_path = episodes_dir / f"{episode.id}.md"
        bundle_path.write_text(bundle)
        index.append(
            {
                "id": episode.id,
                "title": episode.title,
                "kind": episode.kind,
                "commit_shas": episode.commit_shas,
                "paths": episode.paths,
                "bundle": str(bundle_path.relative_to(work_dir)),
            }
        )

    manifest = {
        "tool": "repo-history",
        "version": __version__,
        "method": result.method,
        "ref": ref,
        "head": repo.resolve(ref),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": result.summary,
        "episodes": index,
    }
    (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (work_dir / "analysis.json").write_text(json.dumps(result.to_dict(), indent=2))

    return Materialized(
        work_dir=work_dir, episode_count=len(result.episodes), redactions=redactions
    )
