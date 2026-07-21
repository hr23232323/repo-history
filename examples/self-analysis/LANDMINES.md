# Landmines

Do-not-repeat lessons: approaches that were reverted, abandoned, or removed.

## Don't reintroduce shell-string git invocation (e.g. shell=True or f-string commands).

GitRepo._run deliberately passes ["git", *args] as a list with no shell so that repository refs/paths can't be exploited for argument or shell injection; interpolating them into a shell string would reopen that hole.

_`[observed]` · evidence: 0176e38_

## Don't compute an incremental commit range against a recorded head that no longer exists in the repo (after a rebase or force-push) — flag it and require a full re-run instead.

status detects when the recorded head is missing and reports it rather than silently producing a wrong 'commits since' range that would misrepresent what is new.

_`[observed]` · evidence: 210d2dc_

## Don't keep a second editable copy of SKILL.md; the packaged file in the wheel is the single source of truth and the installed copy is git-ignored.

A locally-installed skill copy would drift from the packaged one, so install-skill writes from the packaged resource and .gitignore excludes .claude/skills/.

_`[observed]` · evidence: 62e5b60_

## Do not pass git refs positionally without --end-of-options and validation; an option-like ref is a real arbitrary-file-write, not just a foot-gun.

`plan --branch '--output=/path'` was parsed by git log as an option and wrote an arbitrary file (confirmed). Because refs also come from repo-controlled data (tags, a committed index.json), the untrusted-repo case makes this an injection surface, not merely user error.

_`[observed]` · evidence: 61ca52e_

## Do not let a single pathologically-named tag abort the whole run; skip the bad ref and continue.

A repo could ship a tag whose name fails ref validation; tags() now skips such a ref instead of aborting the entire analysis, and plan reports the error cleanly instead of tracing back.

_`[observed]` · evidence: 61ca52e_

## Do not treat the checked-in self-analysis example as current source of truth; it is a point-in-time snapshot that drifts.

examples/self-analysis/ is real unedited output captured at one commit and is not regenerated per commit, so it diverges from the live source; the README says to run the tool for up-to-date memory.

_`[observed]` · evidence: 11c5927_

## Do not split git-log records on a byte that can occur in a commit body; it lets a hostile body crash the whole analysis.

A commit body containing the record-separator byte (\x1e) split into a spurious, malformed record and crashed the entire analysis, which is exactly the untrusted-repo case the tool targets. Fixed by NUL (%x00) separation plus greedy body parsing.

_`[observed]` · evidence: 0a4c5ac_

## Do not assume a line-count cap bounds diff size; one minified line can be megabytes.

A single minified line counts as one line but can be megabytes wide, slipping past the line-count cap, so a per-line character cap was added in condense_diff.

_`[observed]` · evidence: 1a49ab7_

## Do not use length-exact or unbounded rules for secret shapes; both leak.

A length-exact rule for a Google (AIza) key would leak a near-miss key in full, so a range is accepted and the code errs toward redacting; separately, an unbounded private-key body match let a BEGIN with no END force a quadratic rescan, so the block is length-bounded.

_`[observed]` · evidence: 9bb739b_

## Do not use bisect_right for tag-boundary episode grouping; it misfiles the tagged commit.

bisect_right classified the commit a tag points at into the next release window instead of the one it names; bisect_left fixes it, covered by a regression test.

_`[observed]` · evidence: 0a4c5ac_

## Do not test security helpers in isolation instead of the render path; a regression in the real path passes silently.

The scrub/fence tests asserted on helper functions, so a regression that dropped scrub() or the dynamic fence in render_bundle would still have passed; tests were moved to run render_bundle/materialize on real commits with a planted secret and an embedded backtick run.

_`[observed]` · evidence: 1b33626_

## Do not let empty repos or corrupt manifests surface raw internal errors.

An unborn HEAD surfaced git's raw internal error and a hand-corrupted manifest threw a bare JSONDecodeError/KeyError; these now raise a clear 'repository has no commits yet' and a BuildError, with episode ids read defensively.

_`[observed]` · evidence: e79d607_

## Don't present an unpublished PyPI install command as if it works today.

The README previously led with `uv tool install repo-history`, but the package was not yet on PyPI; this episode demoted it to a 'once published' note so instructions stay honest.

_`[observed]` · evidence: b4edb23_

## Don't lead the memory output with repo overviews/narrative as if they improve agent accuracy.

Controlled evidence showed overviews help people onboard but don't improve agent accuracy, so TIMELINE/ARCHITECTURE/HOTSPOTS were demoted to onboarding/ and prescriptive guardrails were promoted to lead.

_`[observed]` · evidence: bdf40e4_

## Don't invent rationale a change's evidence doesn't support.

The skill was changed to instruct the map step to omit ungrounded rationale rather than fabricate it, because a confidently-wrong guardrail misleads every future agent that loads it.

_`[observed]` · evidence: eadbfa8_

## Don't parse git log output by splitting on newlines, tabs, or spaces.

Commit subjects and bodies legitimately contain those characters, so the layer uses \x1f/\x1e separators; ordinary delimiters would corrupt parsing on multi-line or punctuated messages.

_`[inferred]` · evidence: 0176e38_

## Don't treat the secret scrubber as a guarantee — it is a defense-in-depth net targeting common high-confidence shapes and deliberately errs toward over-redacting.

security.py's own docstring states it is 'a defense-in-depth safety net, not a guarantee', so it must not be relied on as the sole control against leaking credentials.

_`[inferred]` · evidence: abbceff_
