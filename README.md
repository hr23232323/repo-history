# repo-history

**Git archaeology for AI coding agents.** Most tools index a repo as it exists
*today*. `repo-history` walks the repo's **entire commit history**, works out *why*
it became what it is, and writes durable **engineering memory** your coding agent
can read.

> Senior engineers carry context that isn't in the current code: "we tried X and
> reverted it," "this guard exists because of bug Y," "that abstraction was removed
> for a reason." That knowledge is buried in commits. `repo-history` digs it out and
> writes it down.

Run it once. Commit the output. Every future agent session — and every new
teammate — inherits the repo's memory.

## What it produces

A `.repo-memory/` directory, readable by humans and agents alike:

| File | What's in it |
| --- | --- |
| `TIMELINE.md` | How the architecture evolved, in chapters. |
| `DECISIONS.md` | Decisions inferred from history, with the evidence commits. |
| `LANDMINES.md` | **Do-not-repeat lessons**: reverts, removed abstractions, failed approaches. |
| `ARCHITECTURE.md` | The system today, annotated with how it got here. |
| `HOTSPOTS.md` | Churn, change-coupling, bus-factor. Purely mechanical — zero LLM tokens. |
| `*.json` | Machine-readable mirrors, shaped so an MCP server can serve them. |

### Real output

`repo-history` run on **its own repo** produced 15 decisions and 5 landmines from
7 commits. Every one was reconstructed from commit diffs alone — none of it is
written down in the source:

> **Do not parse git `--numstat` paths as plain strings; rename output has three
> distinct shapes.** git emits renames as `old.py => new.py`,
> `src/{old => new}/file.py`, and `src/{ => sub}/file.py` (empty left side) …
> naive splitting will silently produce bogus paths.

> **Never trust a recorded head sha blindly — check it still exists before
> computing a `since` range.** After a rebase or force-push the head stored in
> `index.json` can vanish from the repo … rather than silently producing a wrong
> (and wrongly-scoped) commit range.

The full, unedited run is in [`examples/self-analysis/`](./examples/self-analysis).

## Install

```bash
uv tool install repo-history        # or: uvx repo-history --help
repo-history install-skill          # adds /repo-history to this project
repo-history install-skill --global # ...or to every project (~/.claude)
```

## Use

```bash
# 1. plan — mechanical pass + episode manifest (deterministic, no LLM, no cost)
repo-history plan --branch main

# 2. analyze — run /repo-history in Claude Code; it fans out subagents over the episodes

# 3. build — render .repo-memory/ from the analyses
repo-history build

# later: only pay for what's new
repo-history status
repo-history plan --since <sha>
```

Then commit `.repo-memory/`.

### Serve it to agents live (MCP)

Instead of (or as well as) committing the files, expose the memory over MCP so an
agent can query it on demand — "why is this file like this?", "anything I should
know before I change X?":

```bash
uv tool install "repo-history[mcp]"
repo-history mcp        # stdio server over ./.repo-memory
```

Tools: `why_is_this(path)`, `list_decisions(topic)`, `list_landmines()`,
`check_before_you_do(proposal)`, `get_timeline()`, `get_hotspots()`. The server
is a pure reader — no LLM, no git, no network.

## How it works

Two **deterministic halves** with the LLM sandwiched between them. The halves only
ever talk through files on disk.

```
git history
    │
    ▼
┌──────────────────── deterministic engine (this package) ─────────────────────┐
│  plan    hotspots · change-coupling · revert detection · drop trivial commits │
│          → segment by release → cluster into "episodes" → condense diffs      │
│          → scrub secrets                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
    │  .repo-memory/.work/  (one Markdown bundle per episode)
    ▼
┌───────────────── LLM orchestrator (/repo-history skill) ─────────────────────┐
│  map     one subagent per episode → {summary, decisions, landmines}          │
│  reduce  roll them up into a coherent narrative                              │
└──────────────────────────────────────────────────────────────────────────────┘
    │  validated JSON
    ▼
┌──────────────────── deterministic engine (this package) ─────────────────────┐
│  build   render .repo-memory/*.md + *.json                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

The LLM step runs **inside Claude Code**, so it uses your existing subscription.
There's no API key to configure and no per-token bill from this tool.

### Why not analyze every commit?

A large repo has tens of thousands of commits; LLM-analyzing each one is slow,
noisy, and expensive. The engine spends tokens only where there's signal:

- **Drop the noise** — lockfiles, minified bundles, generated files.
- **Segment by release/tag** — free, meaningful history windows.
- **Cluster by change-coupling** — commits touching the same files become one *episode*.
- **Always keep landmarks** — reverts get their own episode; they're the richest signal.
- **Condense diffs** — squashed and truncated, never whole file blobs.
- **Run incrementally** — after the first pass, only new commits cost anything.

## Swappable analysis methods

*How* history is read is a plugin. The pipeline shape is fixed, but the method —
what counts as signal, how commits become episodes — is swappable behind a registry.

```bash
repo-history methods                          # list registered methods
repo-history plan --method mechanical         # the built-in, LLM-free method
repo-history plan --method mechanical --json  # inspect a method's output, write nothing
```

Adding one is a single registered file and nothing downstream changes.
See [`docs/adding-a-method.md`](./docs/adding-a-method.md).

## Safety

- **Read-only.** The engine only runs `git log`/`git show`. It never writes to
  your repo, and never uses a shell string (no injection via refs or paths).
- **Secrets are scrubbed** before any repo content reaches an LLM: private keys,
  provider tokens, and `key = "value"` pairs are redacted at the boundary. It
  errs toward redacting. It's a safety net, not a guarantee — don't rely on it to
  make a repo full of live credentials safe.
- **Local-first.** Output is plain files in your repo. Read them, diff them,
  review them before you commit them.

## Development

```bash
uv pip install -e ".[dev]"
uv run pytest
```

Tests run against a synthetic fixture repo built in a temp dir — with a real
rename, a revert, and an annotated tag — so the history shapes that matter are
actually exercised.

## Status

Alpha, but working end-to-end: the deterministic engine, the `/repo-history`
skill, incremental re-runs, and the MCP server are all in place (see the
self-analysis example). The `mechanical` analysis method is the only one shipped
so far; more (and better episode grouping) are where the work goes next.

## License

[MIT](./LICENSE)
