# repo-history

**Git archaeology for AI coding agents.** Most tools index a repo as it exists *today*.
`repo-history` walks the repo's **entire commit history**, distills *why* it became what it
is, and writes durable **engineering memory** that your coding agent can read.

> Senior engineers carry context that isn't in the current code: "we tried X and reverted it,"
> "this guard exists because of bug Y," "this abstraction was removed for a reason." That
> knowledge is buried in commits. `repo-history` digs it out and writes it down.

> ⚠️ **Status: alpha, under active construction.** The engine is being built commit-by-commit.
> Commands print a "not implemented yet" notice until their landing commit.

## What it produces

A committed `.repo-memory/` directory that both humans and agents can read:

| File | What's in it |
| --- | --- |
| `TIMELINE.md` | How the architecture evolved, in chronological chapters. |
| `DECISIONS.md` | Inferred decision log: what changed, *why*, and the evidence commits. |
| `LANDMINES.md` | Do-not-repeat history: reverts, removed abstractions, failed approaches. |
| `ARCHITECTURE.md` | The current structure, annotated with how it was arrived at. |
| `HOTSPOTS.md` | Purely mechanical churn / change-coupling / bus-factor (zero LLM tokens). |
| `*.json` | Machine-readable mirrors, structured so an MCP server can serve them. |

## How it works

`repo-history` splits cleanly into a **deterministic engine** (this Python package) and an
**LLM orchestrator** (a Claude Code skill). The engine never calls an LLM — it does the cheap,
testable mechanical work and hands the interesting parts to the agent.

```
git history
    │
    ▼
┌─────────────────────────── deterministic engine (this package) ───────────────────────────┐
│  1. mechanical pass   hotspots · change-coupling · revert detection · drop trivial commits │
│  2. plan              segment by release/tag → cluster into "episodes" → condense diffs    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
    │  work manifest (.repo-memory/.work/manifest.json)
    ▼
┌──────────────────────── LLM orchestrator (/repo-history skill) ────────────────────────────┐
│  3. map     one subagent per episode → structured JSON (decision, why, landmines, delta)   │
│  4. reduce  roll episode summaries up into a coherent narrative                            │
└────────────────────────────────────────────────────────────────────────────────────────────┘
    │  per-episode analyses
    ▼
┌─────────────────────────── deterministic engine (this package) ───────────────────────────┐
│  5. build             render .repo-memory/*.md + *.json                                    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

Because the LLM step runs *inside* Claude Code, the analysis uses your existing subscription —
there's no API key to configure and no per-token bill from this tool.

### Why not analyze every commit?

A large repo has tens of thousands of commits; analyzing each one with an LLM is slow, noisy,
and expensive. The engine spends tokens only where there's signal:

- **Drop the noise** — lockfile bumps, formatting, whitespace-only changes.
- **Segment by release/tag** — natural, meaningful history windows.
- **Cluster by change-coupling** — commits that co-change files become one "episode."
- **Always keep landmarks** — reverts, large diffs, and notable merges.
- **Condense diffs** — the agent sees squashed, trimmed diffs, not whole file blobs.
- **Run incrementally** — after the first pass, only new commits are processed.

## Install

```bash
# one-off run, no install
uvx repo-history --help

# or install into a tool env
uv tool install repo-history
```

## Usage

```bash
# 1. plan: mechanical pass + episode manifest (deterministic, no LLM)
repo-history plan --repo . --branch main

# 2. analyze: run the /repo-history skill in Claude Code (map/reduce over episodes)

# 3. build: render the .repo-memory/ artifacts from the analyses
repo-history build --repo .

# check incremental state at any time
repo-history status
```

## Design principles

- **Deterministic core, LLM at the edge.** Everything testable lives in Python; the LLM only
  does what's genuinely fuzzy.
- **Read-only and safe.** The engine only *reads* git (`log`/`show`), never mutates your repo,
  and scrubs likely secrets out of diffs before they reach an agent.
- **Local-first.** Output is plain files in your repo. Commit them, diff them, review them.

## License

[MIT](./LICENSE)
