"""Read-only queries over a built .repo-memory directory.

This is the query layer an MCP server (or any consumer) sits on top of. It never
calls an LLM and never touches git: it just reads the JSON artifacts that
``build`` produced. Keeping it separate from the MCP wiring means it can be
tested without the optional ``mcp`` dependency.
"""

from __future__ import annotations

import json
from pathlib import Path


def _tokens(text: str) -> set[str]:
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) > 2}


class RepoMemory:
    """A loaded .repo-memory directory."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.index = self._load("index.json", {})
        self._timeline = self._load("timeline.json", [])
        self._decisions = self._load("decisions.json", [])
        self._landmines = self._load("landmines.json", [])
        self._hotspots = self._load("hotspots.json", [])

    def _load(self, name: str, default):  # noqa: ANN001
        path = self.out_dir / name
        if not path.exists():
            return default
        return json.loads(path.read_text())

    @property
    def has_memory(self) -> bool:
        return (self.out_dir / "index.json").exists()

    def overview(self) -> str:
        path = self.out_dir / "onboarding" / "ARCHITECTURE.md"
        return path.read_text() if path.exists() else ""

    def timeline(self) -> list[dict]:
        return self._timeline

    def decisions(self, topic: str | None = None) -> list[dict]:
        if not topic:
            return self._decisions
        needle = topic.lower()
        return [
            d
            for d in self._decisions
            if needle in d.get("statement", "").lower() or needle in d.get("why", "").lower()
        ]

    def landmines(self) -> list[dict]:
        return self._landmines

    def hotspots(self, limit: int = 20) -> list[dict]:
        return self._hotspots[:limit]

    def why(self, path: str) -> dict:
        """Everything memory knows about why a given file is the way it is."""
        needle = path.strip()
        episodes = [
            t
            for t in self._timeline
            if any(p == needle or p.endswith("/" + needle) for p in t.get("paths", []))
        ]
        ep_ids = {t["id"] for t in episodes}
        return {
            "path": path,
            "episodes": [
                {"id": t["id"], "title": t["title"], "summary": t["summary"]} for t in episodes
            ],
            "decisions": [d for d in self._decisions if d.get("episode") in ep_ids],
            "landmines": [m for m in self._landmines if m.get("episode") in ep_ids],
        }

    def check_before_you_do(self, proposal: str, limit: int = 5) -> list[dict]:
        """Landmines whose wording overlaps a proposed change (a lightweight warning)."""
        wanted = _tokens(proposal)
        scored: list[tuple[int, dict]] = []
        for mine in self._landmines:
            overlap = len(wanted & _tokens(mine.get("lesson", "") + " " + mine.get("detail", "")))
            if overlap:
                scored.append((overlap, mine))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [m for _score, m in scored[:limit]]
