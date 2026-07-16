"""The mechanical analysis method (no LLM).

Cheap, deterministic signals mined straight from commit metadata and churn:
hotspots, change-coupling, reverts. It also groups significant commits into
episodes using release-tag windows and file overlap. This is analysis method #1;
it exists behind the ``Analyzer`` interface so other methods can be swapped in.
"""

from __future__ import annotations

import bisect
import re
from collections import Counter
from dataclasses import dataclass
from itertools import combinations

from .base import AnalysisContext, AnalysisResult, Analyzer, CommitStats, Episode, register
from .util import is_trivial_file

# Commits touching more files than this are structural churn (initial imports,
# mass reformats); counting every file pair would explode and mean nothing.
_MAX_FILES_FOR_COUPLING = 40
# Cap commits per change-episode so a busy release still splits into readable units.
_MAX_COMMITS_PER_EPISODE = 8

_REVERTS_COMMIT_RE = re.compile(r"reverts commit ([0-9a-f]{7,40})", re.IGNORECASE)
_REVERT_SUBJECT_RE = re.compile(r'^Revert "(.*)"\s*$')


@dataclass
class Hotspot:
    path: str
    commits: int  # number of (significant) commits touching this file
    churn: int  # total lines added + deleted
    first_ts: int
    last_ts: int


@dataclass
class CoupledPair:
    a: str
    b: str
    co_changes: int  # commits touching both files
    confidence: float  # co_changes / min(commits(a), commits(b))


@dataclass
class RevertInfo:
    sha: str
    short_sha: str
    subject: str
    reverts_sha: str | None
    reverts_subject: str | None


def detect_reverts(stats: list[CommitStats]) -> list[RevertInfo]:
    """Find commits that undo earlier work, via the message git writes on revert."""
    reverts: list[RevertInfo] = []
    for st in stats:
        c = st.commit
        body_match = _REVERTS_COMMIT_RE.search(c.body or "")
        subject_match = _REVERT_SUBJECT_RE.match(c.subject)
        if not body_match and not subject_match:
            continue
        reverts.append(
            RevertInfo(
                sha=c.sha,
                short_sha=c.short_sha,
                subject=c.subject,
                reverts_sha=body_match.group(1) if body_match else None,
                reverts_subject=subject_match.group(1) if subject_match else None,
            )
        )
    return reverts


def compute_hotspots(ctx: AnalysisContext, sig: list[CommitStats]) -> list[Hotspot]:
    """Rank files by how often significant commits touch them (change frequency)."""
    agg: dict[str, dict[str, int]] = {}
    for st in sig:
        ts = st.commit.timestamp
        seen: set[str] = set()
        for fc in st.changes:
            if is_trivial_file(fc.path):
                continue
            path = ctx.canon(fc.path)
            churn = 0 if fc.binary else fc.added + fc.deleted
            entry = agg.setdefault(
                path, {"commits": 0, "churn": 0, "first": ts, "last": ts}
            )
            entry["churn"] += churn
            entry["first"] = min(entry["first"], ts)
            entry["last"] = max(entry["last"], ts)
            if path not in seen:  # count each file once per commit
                entry["commits"] += 1
                seen.add(path)
    hotspots = [
        Hotspot(path=p, commits=e["commits"], churn=e["churn"], first_ts=e["first"], last_ts=e["last"])
        for p, e in agg.items()
    ]
    hotspots.sort(key=lambda h: (h.commits, h.churn), reverse=True)
    return hotspots


def compute_coupling(
    ctx: AnalysisContext, sig: list[CommitStats], *, min_shared: int = 2
) -> list[CoupledPair]:
    """Find files that repeatedly change together (temporal/logical coupling)."""
    pair_co: Counter[tuple[str, str]] = Counter()
    file_commits: Counter[str] = Counter()
    for st in sig:
        paths = sorted({ctx.canon(p) for p in st.paths if not is_trivial_file(p)})
        if len(paths) > _MAX_FILES_FOR_COUPLING:
            continue
        for p in paths:
            file_commits[p] += 1
        for a, b in combinations(paths, 2):
            pair_co[(a, b)] += 1

    pairs: list[CoupledPair] = []
    for (a, b), co in pair_co.items():
        if co < min_shared:
            continue
        confidence = co / min(file_commits[a], file_commits[b])
        pairs.append(CoupledPair(a=a, b=b, co_changes=co, confidence=round(confidence, 3)))
    pairs.sort(key=lambda p: (p.co_changes, p.confidence), reverse=True)
    return pairs


def group_episodes(
    ctx: AnalysisContext, sig: list[CommitStats], reverts: list[RevertInfo]
) -> list[Episode]:
    """Group significant commits into episodes by tag window + file overlap.

    A new episode starts when the release window changes, the running group
    shares no files with the next commit, or the size cap is hit. Reverts are
    always isolated so "we undid this" reads as its own event.
    """
    revert_shas = {r.sha for r in reverts}
    revert_by_sha = {r.sha: r for r in reverts}
    tag_ts = sorted(t.timestamp for t in ctx.tags)

    episodes: list[Episode] = []
    group: list[CommitStats] = []
    group_paths: set[str] = set()
    group_region: int | None = None

    def flush() -> None:
        nonlocal group, group_paths, group_region
        if not group:
            return
        episodes.append(_make_change_episode(len(episodes) + 1, group, sorted(group_paths)))
        group = []
        group_paths = set()
        group_region = None

    for st in sig:
        # bisect_left so the commit a tag points at belongs to the release it
        # names, not the window after it.
        region = bisect.bisect_left(tag_ts, st.commit.timestamp)
        paths = {ctx.canon(p) for p in st.paths if not is_trivial_file(p)}

        if st.commit.sha in revert_shas:
            flush()
            episodes.append(
                _make_revert_episode(len(episodes) + 1, st, revert_by_sha[st.commit.sha], sorted(paths))
            )
            continue

        crosses_release = group and region != group_region
        no_overlap = bool(group) and group_paths.isdisjoint(paths)
        at_cap = len(group) >= _MAX_COMMITS_PER_EPISODE
        if crosses_release or no_overlap or at_cap:
            flush()

        if not group:
            group_region = region
        group.append(st)
        group_paths |= paths

    flush()
    return episodes


def _make_change_episode(index: int, group: list[CommitStats], paths: list[str]) -> Episode:
    head = group[0].commit.subject
    title = head if len(group) == 1 else f"{head} (+{len(group) - 1} more)"
    return Episode(
        id=f"ep-{index:04d}",
        title=title,
        kind="change",
        commit_shas=[st.commit.sha for st in group],
        paths=paths,
        rationale=(
            f"{len(group)} related commit(s) touching {len(paths)} file(s) "
            f"within one release window."
        ),
    )


def _make_revert_episode(
    index: int, st: CommitStats, revert: RevertInfo, paths: list[str]
) -> Episode:
    target = revert.reverts_subject or revert.reverts_sha or "earlier work"
    return Episode(
        id=f"ep-{index:04d}",
        title=st.commit.subject,
        kind="revert",
        commit_shas=[st.commit.sha],
        paths=paths,
        rationale=f"Reverts {target!r} — a candidate 'do not repeat' lesson.",
    )


@register
class MechanicalAnalyzer(Analyzer):
    key = "mechanical"
    title = "Mechanical"
    description = "Deterministic churn/coupling/revert mining, no LLM."

    def run(self, ctx: AnalysisContext) -> AnalysisResult:
        sig = ctx.significant()
        reverts = detect_reverts(ctx.stats)
        hotspots = compute_hotspots(ctx, sig)
        coupling = compute_coupling(ctx, sig)
        episodes = group_episodes(ctx, sig, reverts)

        summary = {
            "total_commits": len(ctx.stats),
            "significant_commits": len(sig),
            "trivial_commits": sum(1 for s in ctx.stats if s.trivial),
            "merge_commits": sum(1 for s in ctx.stats if s.commit.is_merge),
            "reverts": len(reverts),
            "episodes": len(episodes),
            "tracked_files": len(hotspots),
        }
        sections = {
            "hotspots": hotspots,
            "coupling": coupling,
            "reverts": reverts,
        }
        return AnalysisResult(
            method=self.key, summary=summary, episodes=episodes, sections=sections
        )
