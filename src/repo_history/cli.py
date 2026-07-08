"""Command-line entry point for repo-history.

The CLI is a thin, deterministic shell around the engine. It never calls an LLM
itself: the expensive reasoning is done by the ``/repo-history`` Claude Code skill
(or any agent) that orchestrates ``plan`` -> analysis -> ``build``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Git archaeology for AI coding agents. Distill a repo's history into engineering memory.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"repo-history {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    _version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """repo-history: turn commit history into durable, agent-readable memory."""


@app.command()
def plan(
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository."),
    branch: str = typer.Option("HEAD", "--branch", help="Branch or ref to walk."),
) -> None:
    """Walk history, run mechanical analysis, and emit a work manifest of episodes."""
    typer.echo("`plan` is not implemented yet (coming in an upcoming commit).")
    raise typer.Exit(code=1)


@app.command()
def build(
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository."),
) -> None:
    """Render .repo-memory/ artifacts from completed per-episode analyses."""
    typer.echo("`build` is not implemented yet (coming in an upcoming commit).")
    raise typer.Exit(code=1)


@app.command()
def status(
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository."),
) -> None:
    """Show what has been analyzed and how much history is new since the last run."""
    typer.echo("`status` is not implemented yet (coming in an upcoming commit).")
    raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
