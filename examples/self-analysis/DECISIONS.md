# Decisions

Constraints inferred from history, grounded-first.

## Build the core as a deterministic Python engine using typer (CLI) and pydantic (models); the engine itself never calls an LLM.

Everything testable stays in Python; the expensive, fuzzy reasoning is delegated to the /repo-history skill so analysis runs on the user's existing Claude Code subscription with no API key or per-token bill.

_`[observed]` · evidence: e978a4c_

## Invoke git via subprocess argument-lists, never a shell string, so refs and paths cannot be used for shell injection.

Repository refs and paths are untrusted input; passing them as an arg list (no shell) removes the injection surface.

_`[observed]` · evidence: 0176e38_

## Keep the git layer strictly read-only (log/show/rev-parse/for-each-ref); never write to the repository being analyzed.

The tool inspects a user's repo and must not mutate it.

_`[observed]` · evidence: 0176e38_

## Treat `since` as an exclusive lower bound and walk the `since..ref` range for incremental runs.

Incremental runs should pick up only commits new since the last analysis.

_`[observed]` · evidence: 0176e38_

## Pin author/committer dates and identity in test fixtures to make git-history tests deterministic.

Commit shas and timestamps must be reproducible for assertions to hold across runs and machines.

_`[observed]` · evidence: 0176e38_

## Keep the analysis pipeline fixed but the analysis method swappable: add new methods as one registered Analyzer file returning the common AnalysisResult/Episode contract, without touching downstream materialization or rendering.

Downstream steps depend only on the result contract, so new methods drop in without ripple effects.

_`[observed]` · evidence: ad2b77f_

## Scrub likely secrets (private keys, provider tokens, key=value pairs) and truncate diffs per-file and overall before any repo content is written into an episode bundle for an LLM.

Defense-in-depth so an accidentally-committed credential is not shipped into an agent's context, and bundles stay cheap to read.

_`[observed]` · evidence: abbceff_

## Keep the .work/ directory as git-ignored intermediate scaffolding; only the rendered .repo-memory/*.md and *.json are the durable, committable output.

The work manifest is a hand-off to the LLM step, not a user artifact; the rendered memory is what teams and future agents inherit.

_`[observed]` · evidence: abbceff, 62e5b60_

## Run the LLM half as a Claude Code skill inside the session (using the existing subscription, no API key), with the packaged SKILL.md in the wheel as the single source of truth and the locally-installed copy git-ignored.

Executing in-session avoids an API key, and a single packaged source prevents a second copy from drifting.

_`[observed]` · evidence: 62e5b60_

## Record the analyzed head in index.json and drive re-runs incrementally via `plan --since <sha>` so the expensive LLM pass only ever sees new commits.

Keeps re-runs on already-analyzed repos cheap.

_`[observed]` · evidence: 210d2dc_

## Precede every positional git ref with --end-of-options and validate it to reject leading dashes, whitespace, and control characters.

A ref beginning with '-' is otherwise parsed by git as an option, and since the tool targets untrusted repos, refs also flow from repo-controlled data (tags, a committed index.json), not just the command line.

_`[observed]` · evidence: 61ca52e_

## Keep the MCP SDK an optional [mcp] extra rather than a core dependency.

So the core install stays lean for users who never run the server.

_`[observed]` · evidence: f922f4b_

## Serve memory through RepoMemory, a read-only query layer over the built JSON artifacts, with mcp_server.py only a thin FastMCP adapter over it.

The query layer touches no LLM, git, or network, keeping the serve path cheap and side-effect-free while the adapter just exposes it over stdio.

_`[observed]` · evidence: f922f4b_

## Carry per-episode paths in timeline.json so a file can be mapped to the history that touched it.

why_is_this needs to resolve a file path to the episodes that changed it.

_`[observed]` · evidence: f922f4b_

## Keep every scrubber pattern linear-time (no nested quantifiers) and length-bound the private-key block scan.

Scrubbed diffs come from a possibly-adversarial repo, so a pattern that could catastrophically backtrack is itself a denial-of-service surface.

_`[observed]` · evidence: 9bb739b_

## Separate git-log records with NUL (%x00) and parse the body field greedily with maxsplit.

A separator byte that can legally appear in a commit body must never be usable to split records or truncate the body, since untrusted commit bodies reach the parser.

_`[observed]` · evidence: 0a4c5ac_

## Validate episode ids before using them as filenames, rejecting traversal and dot names.

Ids become filenames and a pluggable analysis method could return '../x' and write outside the episodes dir.

_`[observed]` · evidence: 1a49ab7_

## Mark bundle content as untrusted at the LLM boundary: an inline untrusted-data notice, backtick fences sized to outgrow any embedded run, and a SKILL.md instruction to treat bundle content as data, never instructions.

Repo content flows into an agent and, via committed .repo-memory/, into future sessions, so it can carry text engineered to read as instructions or to break bundle structure.

_`[observed]` · evidence: 1a49ab7_

## Bound diffs by a read cap in raw_diff and a per-line character cap in condense_diff, not by line count alone.

A single generated or minified line can be megabytes wide, so a line-count cap alone lets a memory-exhausting payload through.

_`[observed]` · evidence: 1a49ab7_

## Group episodes with bisect_left and apply the trivial-file filter to episode paths.

bisect_left keeps the commit a tag points at in the release it names rather than the next window, and filtering trivial files stops a shared lockfile from grouping unrelated commits.

_`[observed]` · evidence: 0a4c5ac_

## Lead install docs with `uv tool install git+https://github.com/hr23232323/repo-history` and only mention the PyPI command as pending publication.

The GitHub install works immediately whereas the package is not yet published to PyPI, so docs must reflect what actually works today.

_`[observed]` · evidence: b4edb23_

## State that the AI analysis step requires Claude Code while the plain CLI (history stats, hotspots) works on its own.

Users need to know which capabilities depend on Claude Code so the tool's requirements are not overstated.

_`[observed]` · evidence: b4edb23_

## Lead agent-facing output with prescriptive guardrails (do/don't rules and decision-constraints) and demote repo overviews to human onboarding.

A controlled ablation (AGENTS.md on SWE-bench) found repo overviews don't improve agent accuracy while instructions/constraints do, and landmines are the format with real supporting evidence.

_`[observed]` · evidence: bdf40e4_

## Grade every Decision and Landmine with a `basis` (observed = stated in a commit/PR; inferred = deduced from a diff) and order observed-basis items before inferred ones.

The basis is the trust signal that lets a reader weight each claim and lets the analysis prefer honesty over confident fabrication; readers should meet grounded claims before guesses.

_`[observed]` · evidence: bdf40e4_

## Keep JSON mirrors flat at the root while moving human narrative into onboarding/.

Machine consumers like the MCP server should find the JSON mirrors in one place.

_`[observed]` · evidence: bdf40e4_

## Have the map step grade every decision/landmine `basis` as 'observed' only when the reason is stated outright in a commit/PR/issue, otherwise 'inferred' (and 'inferred' when in doubt).

The basis is the trust signal that lets a reader weight each claim, so it must be assigned honestly.

_`[observed]` · evidence: eadbfa8_

## Phrase decisions as actionable constraints ('Use X, not Y') and landmines as 'don't' guardrails ('Don't reintroduce Z').

Decisions and landmines are the point — they are what an agent loads as guardrails — so they must read as prescriptive rules.

_`[observed]` · evidence: eadbfa8_

## Prefer omission over fabrication: if a change's rationale isn't in the evidence, leave `why` empty or drop the item rather than invent one.

A confidently-wrong guardrail is worse than a missing one; it misleads every future agent that reads it.

_`[observed]` · evidence: eadbfa8_

## Keep the CLI a thin, deterministic shell that orchestrates plan -> analysis -> build; don't put LLM calls in the engine.

_`[inferred]` · evidence: e978a4c_

## Ship commands as visible stubs that exit non-zero with a 'not implemented yet' notice until their landing commit, rather than hiding unbuilt subcommands.

_`[inferred]` · evidence: e978a4c_

## Parse `git log --format` output using \x1f field and \x1e record separators rather than newlines/tabs/spaces.

Those control bytes effectively never appear in commit metadata, so parsing stays unambiguous even when commit messages contain newlines, tabs, or quotes.

_`[inferred]` · evidence: 0176e38_

## Diff and churn commits against the first parent with rename detection (-M --first-parent), so merges report net change and renames are tracked.

_`[inferred]` · evidence: 0176e38_
