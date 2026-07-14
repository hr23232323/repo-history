# Architecture

repo-history is two deterministic halves with an LLM sandwiched between them, and the halves only ever talk to each other through files on disk.

The deterministic engine is a Python package (`src/repo_history/`). `git.py` is the data-source boundary: a read-only `GitRepo` that shells out to git via subprocess argument lists (never shell strings), returning frozen dataclasses (`Commit`, `FileChange`, `Tag`). Diffs are fetched on demand rather than carried on `Commit`, so history walks stay cheap.

`analysis/` is where the pipeline's one deliberate extension point lives. The pipeline *shape* is fixed, but the analysis *method* is a swappable plugin: an `Analyzer` registry hands each method a shared `AnalysisContext` (history loaded once, with rename lineage and tags) and takes back a common `AnalysisResult` (summary + episodes + method-specific sections). Method #1, `mechanical`, uses no LLM at all: it filters trivial/generated files, detects reverts, ranks rename-following hotspots, computes change-coupling, and groups commits into *episodes* by release window and file overlap. Because everything downstream depends only on `AnalysisResult`, a new method is one registered file and nothing else changes.

`work.py` materializes those episodes into `.repo-memory/.work/`: one self-contained Markdown bundle per episode, holding commit messages plus condensed diffs. `security.py` scrubs likely secrets (private keys, provider tokens, `key = "value"` pairs) at this boundary, so nothing sensitive crosses into an LLM's context.

The LLM half is a packaged Claude Code skill (`skill/SKILL.md`, installed via `install-skill`). It reads the bundles, fans out subagents to analyze each episode (map), synthesizes them (reduce), and writes JSON back to disk. Running inside a Claude Code session means it uses an existing subscription instead of an API key. Its output is validated by Pydantic contracts (`models.py`) before it is trusted.

`build.py` then renders the durable artifacts — TIMELINE, DECISIONS, LANDMINES, ARCHITECTURE, HOTSPOTS, plus JSON mirrors shaped for a future MCP server. `state.py` records the analyzed head in `index.json` so re-runs are incremental and only new commits cost tokens.

## How it evolved

- **Scaffold repo-history CLI**: Introduces the src/repo_history package (src-layout, hatchling wheel target) with __init__.py holding __version__ and cli.py as the sole module. The CLI is deliberately a thin typer shell with three commands (plan, build, status) that will later delegate to an engine; the README already fixes the pipeline shape: plan (deterministic) -> LLM analysis via a Claude Code skill -> build (deterministic render into .repo-memory/).
- **Read-only git access layer**: Establishes the data-source boundary for the whole tool: everything downstream consumes frozen dataclasses (Commit, FileChange, Tag) rather than raw git output, and the module is deliberately read-only — no code path writes to the analyzed repository. Diffs are not carried on Commit; they are fetched on demand via raw_diff(sha), keeping history walks cheap.
- **The full plan → skill → build pipeline**: Introduced the pipeline's backbone: `analysis/` (base framework + registry + `mechanical` method + method-agnostic util), `security.py` (secret scrubbing), `work.py` (materialize episodes into `.repo-memory/.work/`), `models.py` (Pydantic contracts for LLM output), `build.py` (render durable artifacts), `state.py` (incremental head tracking), and `skill/SKILL.md` + `skillfile.py` (the packaged Claude Code skill). Every stage talks to the next only through files on disk, so the deterministic CLI and the LLM agent stay decoupled.
