"""Read-only GitHub enrichment: the "why" from PRs, issues, and reviews.

Git commits say *what* changed; the pull request that merged them, the issue it
closed, and the review discussion usually say *why*. This module fetches that
context so the LLM can reason from stated rationale instead of guessing from a
diff.

It is **optional and gracefully degrading**: if the repo has no GitHub remote,
``gh`` isn't installed or authenticated, or a commit has no associated PR, the
source is simply unavailable and callers fall back to commits-only.

The network call is isolated behind an injectable ``runner`` so the parsing —
the part with real logic — is tested offline.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# The GraphQL runner takes (query, variables) and returns the parsed `data` dict.
Runner = Callable[[str, dict], dict]

# Review/PR authors whose text is noise, not rationale.
_BOT_MARKERS = ("[bot]", "dependabot", "github-actions", "copilot", "renovate")

_REMOTE_SLUG = re.compile(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$")

_PULLS_QUERY = """
query($owner:String!, $repo:String!, $oid:GitObjectID!){
  repository(owner:$owner, name:$repo){
    object(oid:$oid){
      ... on Commit {
        associatedPullRequests(first:3){
          nodes{
            number title bodyText
            closingIssuesReferences(first:5){ nodes{ number title bodyText } }
            reviews(first:30){ nodes{ author{ login } state bodyText } }
          }
        }
      }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    issues: tuple[Issue, ...] = ()
    review_notes: tuple[str, ...] = ()  # substantive, human-authored review bodies


def _is_bot(login: str | None) -> bool:
    if not login:
        return True
    lowered = login.lower()
    return any(marker in lowered for marker in _BOT_MARKERS)


def github_slug(repo_path: Path | str) -> tuple[str, str] | None:
    """Return ``(owner, repo)`` if ``origin`` is a github.com remote, else None."""
    try:
        url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except FileNotFoundError:
        return None
    match = _REMOTE_SLUG.search(url)
    if not match:
        return None
    return match.group(1), match.group(2)


def _gh_ready() -> bool:
    try:
        return (
            subprocess.run(
                ["gh", "auth", "status"], capture_output=True, check=False
            ).returncode
            == 0
        )
    except FileNotFoundError:
        return False


def _default_runner(query: str, variables: dict) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-f", f"{key}={value}"]
    out = subprocess.run(args, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "gh graphql call failed")
    return json.loads(out.stdout).get("data", {})


def parse_pulls(data: dict) -> list[PullRequest]:
    """Turn a GraphQL ``data`` payload into PullRequests (bots/empties filtered)."""
    obj = (data or {}).get("repository", {}).get("object") or {}
    nodes = (obj.get("associatedPullRequests") or {}).get("nodes") or []
    pulls: list[PullRequest] = []
    for node in nodes:
        issues = tuple(
            Issue(number=i["number"], title=i.get("title", ""), body=i.get("bodyText", ""))
            for i in (node.get("closingIssuesReferences") or {}).get("nodes", [])
        )
        notes = tuple(
            r["bodyText"].strip()
            for r in (node.get("reviews") or {}).get("nodes", [])
            if r.get("bodyText", "").strip() and not _is_bot((r.get("author") or {}).get("login"))
        )
        pulls.append(
            PullRequest(
                number=node["number"],
                title=node.get("title", ""),
                body=node.get("bodyText", ""),
                issues=issues,
                review_notes=notes,
            )
        )
    return pulls


class GitHubSource:
    """Fetches PR/issue context for commits, with a disk cache."""

    def __init__(
        self,
        owner: str,
        repo: str,
        *,
        runner: Runner | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self._run = runner or _default_runner
        self.cache_dir = cache_dir

    @classmethod
    def detect(
        cls, repo_path: Path | str, *, cache_dir: Path | None = None
    ) -> "GitHubSource | None":
        """Build a source if the repo is on GitHub and ``gh`` is ready, else None."""
        slug = github_slug(repo_path)
        if slug is None or not _gh_ready():
            return None
        return cls(slug[0], slug[1], cache_dir=cache_dir)

    def pulls_for_commit(self, sha: str) -> list[PullRequest]:
        """PRs associated with a commit. Cached; network errors degrade to []."""
        cached = self._cache_read(sha)
        if cached is not None:
            return parse_pulls(cached)
        try:
            data = self._run(
                _PULLS_QUERY, {"owner": self.owner, "repo": self.repo, "oid": sha}
            )
        except (RuntimeError, json.JSONDecodeError):
            return []
        self._cache_write(sha, data)
        return parse_pulls(data)

    def _cache_path(self, sha: str) -> Path | None:
        return self.cache_dir / f"{sha}.json" if self.cache_dir else None

    def _cache_read(self, sha: str) -> dict | None:
        path = self._cache_path(sha)
        if path and path.exists():
            return json.loads(path.read_text())
        return None

    def _cache_write(self, sha: str, data: dict) -> None:
        path = self._cache_path(sha)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
