"""The reusable analysis framework.

The pipeline shape is fixed here; the *method* is swappable. An ``Analyzer``
receives a fully-loaded ``AnalysisContext`` and returns an ``AnalysisResult``.
Downstream steps (episode materialization, artifact rendering) depend only on
``AnalysisResult`` — never on how a particular method computed it — so new
methods can be added without touching anything downstream.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from ..git import Commit, FileChange, GitError, GitRepo, Tag
from .util import build_canonical_map, is_trivial


@dataclass(frozen=True)
class CommitStats:
    """A commit plus its per-file churn and a noise flag, computed once."""

    commit: Commit
    changes: tuple[FileChange, ...]
    trivial: bool

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(c.path for c in self.changes)


@dataclass
class AnalysisContext:
    """Everything a method needs about the history, loaded and cached once."""

    repo: GitRepo
    ref: str
    stats: list[CommitStats]
    canonical: dict[str, str]  # historical path -> current name
    tags: list[Tag]

    def canon(self, path: str) -> str:
        """The current name of a path after following any renames."""
        return self.canonical.get(path, path)

    def significant(self) -> list[CommitStats]:
        """Commits worth reasoning about: not trivial, not merges."""
        return [s for s in self.stats if not s.trivial and not s.commit.is_merge]


@dataclass
class Episode:
    """A coherent chunk of history proposed for one unit of LLM analysis.

    This is the stable contract the LLM/build steps consume, regardless of which
    method produced it.
    """

    id: str
    title: str
    kind: str  # e.g. "change", "revert", "release"
    commit_shas: list[str]
    paths: list[str]
    rationale: str


@dataclass
class AnalysisResult:
    """The common output contract shared by every analysis method."""

    method: str
    summary: dict[str, Any]
    episodes: list[Episode] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "summary": _jsonable(self.summary),
            "episodes": [_jsonable(e) for e in self.episodes],
            "sections": _jsonable(self.sections),
        }


class Analyzer(ABC):
    """A pluggable analysis method. Subclass, set the metadata, implement run."""

    key: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def run(self, ctx: AnalysisContext) -> AnalysisResult:
        ...


# -- registry --------------------------------------------------------------

_REGISTRY: dict[str, type[Analyzer]] = {}


def register(cls: type[Analyzer]) -> type[Analyzer]:
    """Class decorator that registers an analyzer under its ``key``."""
    if not getattr(cls, "key", None):
        raise ValueError(f"{cls.__name__} must define a non-empty `key`")
    if cls.key in _REGISTRY:
        raise ValueError(f"duplicate analyzer key: {cls.key!r}")
    _REGISTRY[cls.key] = cls
    return cls


def get_analyzer(key: str) -> Analyzer:
    if key not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"unknown method {key!r}; available: {known}")
    return _REGISTRY[key]()


def available() -> list[tuple[str, str, str]]:
    """(key, title, description) for every registered method, sorted by key."""
    return sorted(
        (c.key, c.title, c.description) for c in _REGISTRY.values()
    )


# -- loading ---------------------------------------------------------------


def load_context(
    repo: GitRepo,
    ref: str = "HEAD",
    *,
    since: str | None = None,
    max_count: int | None = None,
) -> AnalysisContext:
    """Walk history once and assemble the shared context for any method."""
    try:
        commits = repo.commits(ref, since=since, max_count=max_count)
    except GitError as exc:
        if repo.is_empty():
            raise GitError("repository has no commits yet") from exc
        raise
    stats: list[CommitStats] = []
    renames: list[tuple[str, str]] = []
    for commit in commits:
        changes = tuple(repo.file_changes(commit.sha))
        for fc in changes:
            if fc.old_path is not None:
                renames.append((fc.old_path, fc.path))
        stats.append(
            CommitStats(commit=commit, changes=changes, trivial=is_trivial(changes))
        )
    canonical = build_canonical_map(renames)
    return AnalysisContext(
        repo=repo, ref=ref, stats=stats, canonical=canonical, tags=repo.tags()
    )


def run_analysis(
    repo: GitRepo,
    ref: str = "HEAD",
    *,
    method: str = "mechanical",
    since: str | None = None,
    max_count: int | None = None,
) -> AnalysisResult:
    """Load the context and run the chosen method against it."""
    ctx = load_context(repo, ref, since=since, max_count=max_count)
    return get_analyzer(method).run(ctx)


def _jsonable(value: Any) -> Any:
    """Recursively convert dataclasses/containers into JSON-serializable data."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
