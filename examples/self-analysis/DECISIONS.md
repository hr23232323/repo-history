# Decisions

## Split the tool into a deterministic Python engine and an LLM orchestrator that lives outside it; the engine never calls an LLM.

Keeps everything testable in Python and confines the LLM to what is genuinely fuzzy; because the LLM step runs inside Claude Code it uses the user's existing subscription, so the tool needs no API key and bills no per-token cost.

_evidence: e978a4c_

## Do not LLM-analyze every commit: drop noise, segment by release/tag, cluster co-changing commits into 'episodes', condense diffs, and run incrementally.

A large repo has tens of thousands of commits; analyzing each one is slow, noisy, and expensive, so tokens are spent only where there is signal.

_evidence: e978a4c_

## Ship the CLI surface (plan/build/status) before any implementation, with each command echoing a 'not implemented yet' message and exiting with code 1.

The README declares the project alpha and 'built commit-by-commit'; stubbing the commands fixes the interface up front while making unimplemented paths fail loudly rather than silently succeed.

_evidence: e978a4c_

## The engine only reads git (log/show), never mutates the repo, and scrubs likely secrets out of diffs before they reach an agent; output is plain local files under .repo-memory/.

Stated as a design principle: read-only/safe and local-first, so output can be committed, diffed, and reviewed.

_evidence: e978a4c_

## Shell out to git via subprocess argument lists instead of using a git library or shell strings.

Passing args as a list (never a shell string) means refs and paths supplied by callers cannot be used for shell injection; the module docstring states this explicitly.

_evidence: 0176e38_

## Use ASCII unit/record separators (\x1f, \x1e) as the git log --format delimiters rather than newlines or tabs.

Commit messages legitimately contain newlines, tabs, and quotes; these bytes effectively never appear in commit metadata, so parsing stays unambiguous.

_evidence: 0176e38_

## commits() takes `since` as an exclusive lower bound, walking the `since..ref` range.

This is the mechanism for incremental runs: re-running the tool picks up only commits added after the last processed one.

_evidence: 0176e38_

## file_changes() and raw_diff() are computed against the first parent (--first-parent).

For merge commits this reports the net change introduced by the merge rather than the union of both sides.

_evidence: 0176e38_

## Test against a synthetic git repo built in a temp dir with pinned author/committer identity and timestamps, rather than the tool's own repo or a checked-in fixture.

Determinism, and it lets the fixture deliberately contain the history shapes the tool must handle: a real rename, an annotated tag, and a genuine revert.

_evidence: 0176e38_

## Fix the pipeline shape but make the analysis method a swappable plugin behind an Analyzer registry.

Downstream steps (episode materialization, artifact rendering) depend only on the AnalysisResult/Episode contract, never on how a method computed it, so new methods drop in as one registered file without touching anything downstream. The shared AnalysisContext loads history once (with rename lineage and tags) for any method to reuse.

_evidence: ad2b77f_

## Ship a no-LLM `mechanical` method as method #1: trivial-file filtering, revert detection, rename-following hotspots, change-coupling, and episode grouping by release window + file overlap.

Cheap deterministic signals mined from commit metadata cost nothing and are always available; hotspots need no LLM at all, so HOTSPOTS.md renders even before any analyses exist. Reverts are isolated into their own episodes so 'we undid this' reads as its own event.

_evidence: ad2b77f, 2e50729_

## Scrub secrets and condense diffs before any repo content reaches an LLM.

Defense in depth: an accidentally-committed credential must not get shipped into an agent's context, so security.py redacts private keys, provider tokens, and key=value pairs and deliberately errs toward redacting. Diffs are capped per-file (200 lines) and overall (1500 lines) to keep bundles cheap.

_evidence: abbceff_

## Do the LLM half inside a Claude Code session as a packaged skill instead of calling an API, with SKILL.md shipped in the wheel as the single source of truth.

Running inside a Claude Code session uses the existing subscription, so no API key is needed. Shipping SKILL.md in the package means `uvx repo-history install-skill` drops /repo-history into any project; the locally-installed copy is git-ignored to avoid a second, drifting copy.

_evidence: 62e5b60_

## Validate the agent's map/reduce output with Pydantic contracts (EpisodeAnalysis, Decision, Landmine, Synthesis) before `build` renders anything.

The LLM step communicates with the deterministic build step only through JSON files; typing that boundary means malformed agent output fails at the contract, not in the renderer.

_evidence: 2e50729_

## Record the analyzed head in index.json and make re-runs incremental via `status` + `plan --since`.

The LLM pass is the expensive part, so it should only ever see new history. `status` compares the recorded head to the branch tip and prints the exact `plan --since <sha>` to cover only the gap.

_evidence: 210d2dc_
