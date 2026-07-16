"""Read-only access to a git repository.

Everything here shells out to ``git`` with argument *lists* (never a shell
string), so repository refs and paths can't be used for shell injection. Nothing
in this module writes to the repository.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# A ref beginning with "-" would be parsed by git as an option (e.g.
# `--output=/path`, an arbitrary-file-write). We both reject such refs and pass
# `--end-of-options` before every positional ref as defense in depth. Whitespace
# and control characters are never valid in a ref either.
_UNSAFE_REF = re.compile(r"^-|[\x00-\x1f\x7f]|\s")

# Field and record separators for `git log --format`. Records are separated by
# NUL, which cannot appear in a commit message, so a hostile/odd commit body can
# never split into a spurious record. The body (%b) is the last field and is
# parsed greedily, so an embedded field separator in it can't truncate it either.
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x00"
_LOG_FIELDS = ["%H", "%h", "%an", "%ae", "%at", "%P", "%s", "%b"]
# `%x00` is a git format directive that emits a NUL in the *output*; a literal
# NUL can't be passed in the argv format string, so it must not appear here.
_LOG_FORMAT = _FIELD_SEP.join(_LOG_FIELDS) + "%x00"


class GitError(RuntimeError):
    """Raised when a git command fails or a path is not a git repository."""


def _check_ref(ref: str) -> str:
    """Reject refs that could be parsed as git options or aren't valid refs."""
    if not ref or _UNSAFE_REF.search(ref):
        raise GitError(f"unsafe or invalid git ref: {ref!r}")
    return ref


@dataclass(frozen=True)
class FileChange:
    """A single file touched by a commit, with line churn from ``--numstat``."""

    path: str
    added: int
    deleted: int
    old_path: str | None = None  # set when the file was renamed/moved
    binary: bool = False

    @property
    def renamed(self) -> bool:
        return self.old_path is not None


@dataclass(frozen=True)
class Commit:
    """A commit's metadata (no diff). Diffs are fetched on demand."""

    sha: str
    short_sha: str
    author_name: str
    author_email: str
    timestamp: int  # author time, unix seconds
    parents: tuple[str, ...]
    subject: str
    body: str

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def is_root(self) -> bool:
        return len(self.parents) == 0

    @property
    def message(self) -> str:
        return f"{self.subject}\n\n{self.body}".strip()


@dataclass(frozen=True)
class Tag:
    name: str
    sha: str  # the commit the tag ultimately points at
    timestamp: int


class GitRepo:
    """A read-only handle on a local git repository."""

    def __init__(self, path: Path | str = ".") -> None:
        self.path = Path(path).resolve()
        if not self._is_git_repo():
            raise GitError(f"not a git repository: {self.path}")

    # -- low-level ---------------------------------------------------------

    def _run(self, *args: str, check: bool = True) -> str:
        """Run ``git <args>`` in the repo and return stdout as text."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError as exc:  # git not installed
            raise GitError("git executable not found on PATH") from exc
        if check and result.returncode != 0:
            cmd = " ".join(args)
            raise GitError(f"`git {cmd}` failed: {result.stderr.strip()}")
        return result.stdout

    def _is_git_repo(self) -> bool:
        try:
            out = self._run("rev-parse", "--is-inside-work-tree", check=False)
        except GitError:
            return False
        return out.strip() == "true"

    # -- refs --------------------------------------------------------------

    def is_empty(self) -> bool:
        """True if the repository has no commits yet (unborn HEAD)."""
        try:
            self.resolve("HEAD")
        except GitError:
            return True
        return False

    def resolve(self, ref: str) -> str:
        """Resolve a ref (branch, tag, short sha, HEAD) to a full commit sha."""
        _check_ref(ref)
        return self._run(
            "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"
        ).strip()

    # -- history walk ------------------------------------------------------

    def commits(
        self,
        ref: str = "HEAD",
        *,
        since: str | None = None,
        max_count: int | None = None,
        first_parent: bool = False,
    ) -> list[Commit]:
        """Return commits in chronological order (oldest first).

        ``since`` is an *exclusive* lower bound ref: passing it walks the
        ``since..ref`` range, which is how incremental runs pick up only new
        commits. ``first_parent`` follows only the mainline through merges.
        """
        _check_ref(ref)
        if since is not None:
            _check_ref(since)
        rangespec = f"{since}..{ref}" if since else ref
        args = ["log", f"--format={_LOG_FORMAT}", "--reverse"]
        if max_count is not None:
            args += ["--max-count", str(max_count)]
        if first_parent:
            args.append("--first-parent")
        args += ["--end-of-options", rangespec]
        out = self._run(*args)
        return [_parse_commit(record) for record in _split_records(out)]

    def commit(self, sha: str) -> Commit:
        """Fetch a single commit's metadata by sha or ref."""
        commits = self.commits(sha, max_count=1)
        if not commits:
            raise GitError(f"no such commit: {sha}")
        return commits[0]

    def file_changes(self, sha: str) -> list[FileChange]:
        """Files touched by a commit, with per-file line churn.

        Uses ``--numstat`` against the first parent so merge commits report the
        net change rather than the union of both sides.
        """
        _check_ref(sha)
        out = self._run(
            "show", "--numstat", "--format=", "-M", "--first-parent",
            "--end-of-options", sha,
        )
        changes: list[FileChange] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            added_s, deleted_s, rest = line.split("\t", 2)
            binary = added_s == "-" or deleted_s == "-"
            added = 0 if binary else int(added_s)
            deleted = 0 if binary else int(deleted_s)
            new_path, old_path = _parse_numstat_path(rest)
            changes.append(
                FileChange(
                    path=new_path,
                    added=added,
                    deleted=deleted,
                    old_path=old_path,
                    binary=binary,
                )
            )
        return changes

    def raw_diff(self, sha: str, *, max_chars: int = 2_000_000) -> str:
        """The unified diff a commit introduced (vs its first parent).

        Reading stops after ``max_chars`` so a single commit that adds a huge
        (possibly generated) file can't exhaust memory on an untrusted repo.
        """
        _check_ref(sha)
        proc = subprocess.Popen(
            [
                "git", "show", "--format=", "--first-parent", "--no-color",
                "--end-of-options", sha,
            ],
            cwd=self.path,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            assert proc.stdout is not None
            out = proc.stdout.read(max_chars)
            truncated = proc.stdout.read(1) != ""  # is there more we're dropping?
        finally:
            proc.stdout.close()  # type: ignore[union-attr]
            proc.terminate()
            proc.wait()
        if truncated:
            out += f"\n... [diff truncated: exceeded {max_chars} chars]"
        return out

    def tags(self) -> list[Tag]:
        """All tags, resolved to their commit and sorted oldest-first."""
        out = self._run(
            "for-each-ref",
            "--format=%(refname:short)" + _FIELD_SEP + "%(objectname)",
            "refs/tags",
        )
        tags: list[Tag] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            name, _obj = line.split(_FIELD_SEP, 1)
            # ^{commit} dereferences annotated tags to the commit they wrap.
            # A repo could ship a pathologically-named tag; skip rather than abort.
            try:
                sha = self.resolve(name)
            except GitError:
                continue
            ts = int(
                self._run(
                    "show", "-s", "--format=%at", "--end-of-options", sha
                ).strip()
            )
            tags.append(Tag(name=name, sha=sha, timestamp=ts))
        return sorted(tags, key=lambda t: t.timestamp)


# -- parsing helpers -------------------------------------------------------


def _split_records(out: str) -> list[str]:
    return [rec for rec in out.split(_RECORD_SEP) if rec.strip()]


def _parse_commit(record: str) -> Commit:
    # maxsplit keeps the body (last field) intact even if it contains a field
    # separator: everything after the 7th separator is the body, verbatim.
    fields = record.strip("\n").split(_FIELD_SEP, len(_LOG_FIELDS) - 1)
    if len(fields) < len(_LOG_FIELDS):
        fields += [""] * (len(_LOG_FIELDS) - len(fields))
    sha, short_sha, an, ae, at, parents, subject, body = fields
    parent_shas = tuple(p for p in parents.split() if p)
    return Commit(
        sha=sha,
        short_sha=short_sha,
        author_name=an,
        author_email=ae,
        timestamp=int(at) if at else 0,
        parents=parent_shas,
        subject=subject,
        body=body.strip("\n"),
    )


def _parse_numstat_path(raw: str) -> tuple[str, str | None]:
    """Return ``(new_path, old_path_or_None)`` from a numstat path field.

    Renames appear either as ``old => new`` or with a common prefix/suffix
    factored out as ``src/{old => new}/file.py``.
    """
    if "{" in raw and " => " in raw:
        prefix, rest = raw.split("{", 1)
        inner, suffix = rest.split("}", 1)
        old_inner, new_inner = inner.split(" => ", 1)
        old = _collapse_slashes(prefix + old_inner + suffix)
        new = _collapse_slashes(prefix + new_inner + suffix)
        return new, old
    if " => " in raw:
        old, new = raw.split(" => ", 1)
        return new.strip(), old.strip()
    return raw, None


def _collapse_slashes(path: str) -> str:
    while "//" in path:
        path = path.replace("//", "/")
    return path
