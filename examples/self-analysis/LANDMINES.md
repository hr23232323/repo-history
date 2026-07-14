# Landmines

Do-not-repeat lessons: approaches that were reverted, abandoned, or removed.

## Do not parse git --numstat paths as plain strings; rename output has three distinct shapes.

git emits renames as `old.py => new.py`, `src/{old => new}/file.py`, and `src/{ => sub}/file.py` (empty left side). A dedicated _parse_numstat_path helper handles all three and is parametrized-tested for each; naive splitting will silently produce bogus paths.

_evidence: 0176e38_

## Git subprocesses in tests must not inherit the developer's git config.

The fixture invokes git with `-c commit.gpgsign=false -c core.autocrlf=false` and an env that pins GIT_AUTHOR_*/GIT_COMMITTER_* name, email, and date. Without this, a contributor with commit signing or autocrlf enabled would get hangs or non-deterministic shas and diffs.

_evidence: 0176e38_

## Never trust a recorded head sha blindly — check it still exists before computing a `since` range.

After a rebase or force-push the head stored in index.json can vanish from the repo. read_status resolves it and sets head_missing, telling the user to re-run a full plan, rather than silently producing a wrong (and wrongly-scoped) commit range.

_evidence: 210d2dc_

## Do not compute file change-coupling over huge commits; skip anything touching more than ~40 files.

Initial imports and mass reformats are structural churn. Counting every file pair in them is quadratic and produces couplings that mean nothing, so _MAX_FILES_FOR_COUPLING drops those commits from the pairing pass.

_evidence: ad2b77f_

## Do not commit the .work/ scaffolding, and do not keep a second copy of SKILL.md in .claude/skills/.

materialize() writes a .gitignore into .repo-memory/ so the intermediate work dir stays out of users' commits, and .gitignore excludes .claude/skills/ because the packaged src/repo_history/skill/SKILL.md is the single source of truth — a checked-in local copy would drift from it.

_evidence: abbceff, 62e5b60_
