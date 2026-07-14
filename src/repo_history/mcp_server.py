"""A local MCP server that serves .repo-memory to coding agents.

This is a thin adapter over ``RepoMemory``: no LLM, no git, no network. It exposes
the distilled history as tools an agent can call live ("why is this file like
this?", "what should I know before changing X?"). Requires the optional ``mcp``
dependency: ``uv tool install "repo-history[mcp]"``.
"""

from __future__ import annotations

from pathlib import Path

from .memory import RepoMemory


def build_server(out_dir: Path):  # noqa: ANN201 (FastMCP, imported lazily)
    """Construct the FastMCP server bound to a .repo-memory directory."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised via the CLI
        raise RuntimeError(
            "the MCP server needs the optional dependency: "
            'install with `uv tool install "repo-history[mcp]"`'
        ) from exc

    memory = RepoMemory(out_dir)
    server = FastMCP("repo-history")

    @server.tool()
    def why_is_this(path: str) -> dict:
        """Why is a given file the way it is? Returns the episodes, decisions, and
        landmines from history that touch it."""
        return memory.why(path)

    @server.tool()
    def list_decisions(topic: str = "") -> list[dict]:
        """List engineering decisions inferred from history, optionally filtered by topic."""
        return memory.decisions(topic or None)

    @server.tool()
    def list_landmines() -> list[dict]:
        """List do-not-repeat lessons: reverts, removed abstractions, failed approaches."""
        return memory.landmines()

    @server.tool()
    def check_before_you_do(proposal: str) -> list[dict]:
        """Given a change you're about to make, surface any past landmines that resemble it."""
        return memory.check_before_you_do(proposal)

    @server.tool()
    def get_timeline() -> list[dict]:
        """The chronological evolution of the codebase."""
        return memory.timeline()

    @server.tool()
    def get_hotspots(limit: int = 20) -> list[dict]:
        """The most-changed files (mechanical churn signal)."""
        return memory.hotspots(limit)

    return server, memory
