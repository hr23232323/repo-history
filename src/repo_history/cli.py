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
    method: str = typer.Option(
        "mechanical", "--method", "-m", help="Analysis method to run (see `methods`)."
    ),
    since: str = typer.Option(
        None,
        "--since",
        help="Only analyze commits after this sha (incremental; see `status`).",
    ),
    max_count: int = typer.Option(
        None, "--max-count", help="Only walk the most recent N commits."
    ),
    out: Path = typer.Option(
        None, "--out", help="Output directory (default: <repo>/.repo-memory)."
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print the result as JSON and skip writing to disk."
    ),
) -> None:
    """Walk history with the chosen analysis method and write a work manifest.

    The manifest (episode bundles + condensed, secret-scrubbed diffs) is what the
    ``/repo-history`` skill reads to run its per-episode analysis.
    """
    import json

    from .analysis import get_analyzer, run_analysis
    from .git import GitError, GitRepo
    from .work import materialize

    try:
        git_repo = GitRepo(repo)
        get_analyzer(method)  # validate the method name early with a clear error
        result = run_analysis(
            git_repo, branch, method=method, since=since, max_count=max_count
        )
    except (GitError, KeyError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if not result.episodes:
        typer.secho("no episodes to analyze (history is already covered)", bold=True)
        return

    if as_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
        return

    _print_summary(result)
    out_dir = out or (repo / ".repo-memory")
    materialized = materialize(git_repo, result, out_dir, ref=branch)
    typer.secho(
        f"\nwrote {materialized.episode_count} episode bundle(s) to "
        f"{materialized.work_dir}",
        bold=True,
    )
    typer.echo(f"redacted {materialized.redactions} likely secret(s)")
    typer.echo("next: run the /repo-history skill in Claude Code, then `repo-history build`")


def _print_summary(result) -> None:  # noqa: ANN001 (AnalysisResult, imported lazily)
    typer.secho(f"method: {result.method}", bold=True)
    for key, value in result.summary.items():
        typer.echo(f"  {key.replace('_', ' ')}: {value}")
    hotspots = result.sections.get("hotspots", [])[:5]
    if hotspots:
        typer.secho("top hotspots:", bold=True)
        for h in hotspots:
            typer.echo(f"  {h.commits:>3} commits  {h.path}")
    if result.episodes:
        typer.secho(f"episodes ({len(result.episodes)}):", bold=True)
        for ep in result.episodes[:10]:
            typer.echo(f"  [{ep.kind}] {ep.id}  {ep.title}")


@app.command(name="install-skill")
def install_skill(
    to_global: bool = typer.Option(
        False, "--global", help="Install to ~/.claude instead of ./.claude."
    ),
) -> None:
    """Install the /repo-history Claude Code skill into a project or your home dir."""
    from pathlib import Path as _Path

    from .skillfile import install_skill as _install

    base = _Path.home() if to_global else _Path(".")
    dest = _install(base)
    typer.secho(f"installed skill to {dest}", bold=True)
    typer.echo("invoke it in Claude Code with: /repo-history")


@app.command()
def methods() -> None:
    """List the available analysis methods."""
    from .analysis import available

    for key, title, description in available():
        typer.secho(f"{key}", bold=True, nl=False)
        typer.echo(f"  {title} — {description}")


@app.command()
def build(
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository."),
    out: Path = typer.Option(
        None, "--out", help="Output directory (default: <repo>/.repo-memory)."
    ),
) -> None:
    """Render .repo-memory/ artifacts from completed per-episode analyses."""
    from .build import BuildError, build_artifacts

    out_dir = out or (repo / ".repo-memory")
    try:
        result = build_artifacts(out_dir)
    except BuildError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.secho(f"wrote {len(result.files)} artifact(s) to {out_dir}", bold=True)
    typer.echo(
        f"  {result.episodes} episodes · {result.decisions} decisions · "
        f"{result.landmines} landmines"
    )
    if result.episodes == 0:
        typer.echo("  (no episode analyses found — run the /repo-history skill first)")


@app.command()
def status(
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository."),
    out: Path = typer.Option(
        None, "--out", help="Output directory (default: <repo>/.repo-memory)."
    ),
) -> None:
    """Show what has been analyzed and how much history is new since the last run."""
    from .git import GitError, GitRepo
    from .state import read_status

    out_dir = out or (repo / ".repo-memory")
    try:
        git_repo = GitRepo(repo)
    except GitError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    state = read_status(git_repo, out_dir)
    if not state.has_memory:
        typer.echo(f"no memory at {out_dir}")
        typer.echo("run: repo-history plan   (then the /repo-history skill, then build)")
        return

    typer.secho(f"memory at {out_dir}", bold=True)
    typer.echo(f"  method: {state.method}")
    typer.echo(f"  ref:    {state.ref} @ {str(state.head)[:8]}")
    typer.echo(f"  built:  {state.built_at}")
    counts = state.counts
    typer.echo(
        f"  {counts.get('episodes', 0)} episodes · {counts.get('decisions', 0)} decisions"
        f" · {counts.get('landmines', 0)} landmines"
    )

    if state.head_missing:
        typer.secho(
            "\nthe recorded head is not in this repo (rebased or force-pushed?);"
            " re-run a full plan",
            fg=typer.colors.YELLOW,
        )
        return
    if state.new_commits == 0:
        typer.secho("\nup to date", fg=typer.colors.GREEN)
    else:
        typer.secho(f"\n{state.new_commits} new commit(s) since the last build", bold=True)
        typer.echo(f"  repo-history plan --since {str(state.head)[:12]}")


@app.command()
def mcp(
    repo: Path = typer.Option(Path("."), "--repo", help="Path to the git repository."),
    out: Path = typer.Option(
        None, "--out", help="Memory directory to serve (default: <repo>/.repo-memory)."
    ),
) -> None:
    """Serve .repo-memory over MCP (stdio) so agents can query it live."""
    out_dir = out or (repo / ".repo-memory")
    if not (out_dir / "index.json").exists():
        typer.secho(
            f"no memory at {out_dir}; run plan -> /repo-history -> build first",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    from .mcp_server import build_server

    try:
        server, _memory = build_server(out_dir)
    except RuntimeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    server.run()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
