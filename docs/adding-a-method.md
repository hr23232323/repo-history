# Adding an analysis method

The pipeline shape is fixed; the *way you read history* is not. An analysis
method decides **what counts as signal** and **how history is chunked into
episodes**. Everything downstream — episode bundles, the LLM map/reduce, the
rendered artifacts — depends only on the shared result contract, so a new method
never requires touching the rest of the tool.

```
load history once   ->   [ your method ]   ->   episodes + findings   ->   bundles -> LLM -> artifacts
   (framework)              (swappable)            (fixed contract)              (framework)
```

## The contract

You get an `AnalysisContext` and return an `AnalysisResult`.

```python
@dataclass
class AnalysisContext:
    repo: GitRepo                 # read-only git access
    ref: str
    stats: list[CommitStats]      # every commit + its per-file churn + a trivial flag
    canonical: dict[str, str]     # historical path -> current name (rename lineage)
    tags: list[Tag]

    def canon(self, path) -> str          # a path's current name after renames
    def significant(self) -> list[CommitStats]   # non-trivial, non-merge commits
```

```python
@dataclass
class AnalysisResult:
    method: str
    summary: dict[str, Any]        # headline numbers, shown by the CLI
    episodes: list[Episode]        # THE thing downstream consumes
    sections: dict[str, Any]       # method-specific findings (rendered into artifacts)
```

An `Episode` is one unit of LLM analysis: `id`, `title`, `kind`
(`change` / `revert` / `release`), the `commit_shas` it covers, the `paths` it
touches, and a `rationale` for why these commits belong together.

Only `episodes` is load-bearing. `sections` is free-form: it's how `mechanical`
ships hotspots and coupling into `HOTSPOTS.md`.

## Write one

Create `src/repo_history/analysis/my_method.py`:

```python
from .base import AnalysisContext, AnalysisResult, Analyzer, Episode, register


@register
class MyAnalyzer(Analyzer):
    key = "my-method"                       # what `--method` takes
    title = "My method"
    description = "One line, shown by `repo-history methods`."

    def run(self, ctx: AnalysisContext) -> AnalysisResult:
        episodes = [
            Episode(
                id=f"ep-{i + 1:04d}",
                title=st.commit.subject,
                kind="change",
                commit_shas=[st.commit.sha],
                paths=sorted({ctx.canon(p) for p in st.paths}),
                rationale="one commit per episode",
            )
            for i, st in enumerate(ctx.significant())
        ]
        return AnalysisResult(
            method=self.key,
            summary={"episodes": len(episodes)},
            episodes=episodes,
            sections={},
        )
```

Register it by importing the module in `analysis/__init__.py` (the `@register`
decorator does the rest), then:

```bash
repo-history methods                      # your method is listed
repo-history plan --method my-method      # and runnable
repo-history plan --method my-method --json   # inspect the result without writing
```

`--json` prints the full result and skips writing to disk, which makes it easy to
compare two methods on the same repo.

## Ideas worth trying

- **release-windows** — one episode per git tag; good for repos that ship often.
- **coupling-graph** — build episodes from clusters in the change-coupling graph
  rather than from commit adjacency, so logically-related work groups even when
  it was committed weeks apart.
- **author-arc** — segment by who was working on what, to surface ownership
  handoffs and the context that got lost with them.
- **hotspot-first** — only analyze episodes that touch the top-N churn files, to
  spend tokens where the code actually changes.

## Rules of thumb

- Keep methods **deterministic and LLM-free**. The LLM runs later, on your
  episodes. A method that calls an LLM is possible but gives up the free,
  fast, fully-testable property the framework is built around.
- **Drop noise.** `ctx.significant()` already excludes merges and
  lock/generated-file-only commits; `util.is_trivial_file` filters individual
  files.
- **Isolate reverts.** A reverted change is the highest-signal thing in a repo's
  history — give it its own episode so the LLM writes it up as a landmine.
- **Episodes are a token budget.** Fewer, well-grouped episodes = a cheaper run.
  Cap how many commits land in one episode so a busy period still splits into
  readable units.
