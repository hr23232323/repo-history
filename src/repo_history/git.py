"""Read-only access to a git repository.

Everything here shells out to ``git`` with argument *lists* (never a shell
string), so repository refs and paths can't be used for shell injection. Nothing
in this module writes to the repository.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Field and record separators for `git log --format`. These bytes effectively
# never appear in commit metadata, so parsing stays unambiguous even when commit
# messages contain newlines, tabs, or quotes.
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"
_LOG_FORMAT = _FIELD_SEP.join(
    ["%H", "%h", "%an", "%ae", "%at", "%P", "%s", "%b"]
) + _RECORD_SEP


class GitError(RuntimeError):
    """Raised when a git command fails or a path is not a git repository."""


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

    def resolve(self, ref: str) -> str:
        """Resolve a ref (branch, tag, short sha, HEAD) to a full commit sha."""
        return self._run("rev-parse", "--verify", f"{ref}^{{commit}}").strip()

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
        rangespec = f"{since}..{ref}" if since else ref
        args = ["log", f"--format={_LOG_FORMAT}", "--reverse"]
        if max_count is not None:
            args += ["--max-count", str(max_count)]
        if first_parent:
            args.append("--first-parent")
        args.append(rangespec)
        out = self._run(*args)
        return [_parse_commit(record) for record in _split_records(out)]

    def file_changes(self, sha: str) -> list[FileChange]:
        """Files touched by a commit, with per-file line churn.

        Uses ``--numstat`` against the first parent so merge commits report the
        net change rather than the union of both sides.
        """
        out = self._run(
            "show", "--numstat", "--format=", "-M", "--first-parent", sha
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

    def raw_diff(self, sha: str) -> str:
        """The full unified diff a commit introduced (vs its first parent)."""
        return self._run(
            "show", "--format=", "--first-parent", "--no-color", sha
        )

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
            sha = self.resolve(name)
            ts = int(self._run("show", "-s", "--format=%at", sha).strip())
            tags.append(Tag(name=name, sha=sha, timestamp=ts))
        return sorted(tags, key=lambda t: t.timestamp)


# -- parsing helpers -------------------------------------------------------


def _split_records(out: str) -> list[str]:
    return [rec for rec in out.split(_RECORD_SEP) if rec.strip()]


def _parse_commit(record: str) -> Commit:
    fields = record.strip("\n").split(_FIELD_SEP)
    # body (%b) may be empty and is the last field.
    if len(fields) < 8:
        fields += [""] * (8 - len(fields))
    sha, short_sha, an, ae, at, parents, subject, body = fields[:8]
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
