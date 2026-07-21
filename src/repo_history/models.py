"""Typed contracts for the LLM step's output.

These are the schemas the ``/repo-history`` skill fills in: one
``EpisodeAnalysis`` per episode (the map step) and one ``Synthesis`` for the
whole repo (the reduce step). Keeping them as Pydantic models means the agent's
JSON is validated before ``build`` ever renders it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# How well-grounded a claim is. "observed" = stated outright in a commit message,
# PR, or issue; "inferred" = deduced from a diff and should be trusted less. This
# is the trust signal that lets a reader (or agent) weight each claim — and lets
# the analysis prefer honesty ("inferred", or omission) over confident fabrication.
Basis = Literal["observed", "inferred"]


class Decision(BaseModel):
    """An engineering decision, framed as a forward-looking constraint."""

    statement: str  # phrased as guidance, e.g. "Use server-side sessions, not JWTs"
    why: str = ""  # the reason, as far as history reveals it
    basis: Basis = "inferred"
    evidence: list[str] = Field(default_factory=list)  # commit shas / PRs / episode ids


class Landmine(BaseModel):
    """A do-not-repeat lesson: a reverted approach, removed abstraction, etc."""

    lesson: str  # the takeaway, phrased as a "don't" guardrail
    detail: str = ""  # what happened and why it didn't work
    basis: Basis = "inferred"
    evidence: list[str] = Field(default_factory=list)


class EpisodeAnalysis(BaseModel):
    """The map-step output for a single episode."""

    id: str
    title: str
    summary: str  # 1-3 sentences for the timeline
    kind: str = "change"
    architecture_note: str | None = None  # how structure changed, if it did
    decisions: list[Decision] = Field(default_factory=list)
    landmines: list[Landmine] = Field(default_factory=list)


class Synthesis(BaseModel):
    """The reduce-step output: a repo-wide view built from the episodes."""

    architecture_overview: str = ""
    narrative: str = ""
