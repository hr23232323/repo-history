"""Typed contracts for the LLM step's output.

These are the schemas the ``/repo-history`` skill fills in: one
``EpisodeAnalysis`` per episode (the map step) and one ``Synthesis`` for the
whole repo (the reduce step). Keeping them as Pydantic models means the agent's
JSON is validated before ``build`` ever renders it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Decision(BaseModel):
    """An engineering decision inferred from history."""

    statement: str  # what was decided, e.g. "Moved sessions from JWT to server-side"
    why: str = ""  # the reason, as far as history reveals it
    evidence: list[str] = Field(default_factory=list)  # commit shas / episode ids


class Landmine(BaseModel):
    """A do-not-repeat lesson: a reverted approach, removed abstraction, etc."""

    lesson: str  # the takeaway, phrased as guidance
    detail: str = ""  # what happened and why it didn't work
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
