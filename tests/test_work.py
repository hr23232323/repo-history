"""Tests for secret scrubbing, diff condensing, and materialization."""

from __future__ import annotations

import json

import pytest
from conftest import FixtureRepo, _git

from repo_history.git import GitRepo

from repo_history.analysis import Episode, run_analysis
from repo_history.security import scrub
from repo_history.work import (
    WORK_DIRNAME,
    _check_episode_id,
    _fence,
    condense_diff,
    materialize,
    render_bundle,
)


@pytest.mark.parametrize(
    "text,leak",
    [
        ("AWS_KEY=AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
        (
            "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        ),
        ("password = 'hunter2secret'", "hunter2secret"),
        # shapes the first version of the scrubber missed:
        (
            "auth = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
            "dozjgNryP4J3jVmNHl0w5N",
        ),
        ("key: AIzaSyA1234567890abcdefghijklmnopqrstuvw", "AIzaSyA1234567890abcdefghijklmnopqrstuvw"),
        ("STRIPE=sk_live_abcdef1234567890ABCDEF", "sk_live_abcdef1234567890ABCDEF"),
        ("openai sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345", "sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345"),
        ("github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz123456", "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz123456"),
        ("DATABASE_URL=postgres://admin:sup3rs3cret@db.example.com:5432/app", "sup3rs3cret"),
        # a quoted value containing spaces must be redacted in full
        ('password = "correct horse battery staple"', "correct horse battery staple"),
    ],
)
def test_scrub_redacts_secrets(text: str, leak: str) -> None:
    scrubbed, count = scrub(text)
    assert count >= 1
    assert leak not in scrubbed, f"secret leaked: {scrubbed}"


def test_scrub_connection_string_keeps_context() -> None:
    scrubbed, _ = scrub("postgres://admin:sup3rs3cret@db.example.com/app")
    assert "sup3rs3cret" not in scrubbed
    # scheme, user and host survive so the diff still reads sensibly
    assert "postgres://admin:" in scrubbed
    assert "@db.example.com/app" in scrubbed


def test_scrub_leaves_clean_text_untouched() -> None:
    text = "def add(a, b):\n    return a + b\n"
    scrubbed, count = scrub(text)
    assert count == 0
    assert scrubbed == text


def test_scrub_private_key_block() -> None:
    text = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    scrubbed, count = scrub(text)
    assert count == 1
    assert "PRIVATE KEY-----\nMIIE" not in scrubbed
    assert "[REDACTED PRIVATE KEY]" in scrubbed


def test_condense_diff_truncates_large_files() -> None:
    diff = "diff --git a/big.py b/big.py\n" + "\n".join(
        f"+line {i}" for i in range(500)
    )
    condensed = condense_diff(diff, max_file_lines=50, max_total_lines=1000)
    assert "lines truncated" in condensed
    assert len(condensed.splitlines()) <= 60


def test_condense_diff_caps_a_giant_single_line() -> None:
    # A minified line is one "line" but megabytes wide — the line-count cap alone
    # would let it through, so there is a per-line char cap too.
    diff = "diff --git a/app.min.js b/app.min.js\n+" + "x" * 100_000
    condensed = condense_diff(diff)
    assert "more chars]" in condensed
    assert len(condensed) < 2_000


def test_fence_outgrows_embedded_backticks() -> None:
    assert _fence("no backticks") == "```"
    # content containing a ``` run needs a longer fence to stay enclosed
    assert len(_fence("evil ``` closes early")) >= 4
    assert len(_fence("````" )) >= 5


def _one_commit_repo(tmp_path, name: str, filename: str, content: str):
    d = tmp_path / name
    d.mkdir()
    _git(d, "init", "-b", "main", ts=1_700_000_000)
    (d / filename).write_text(content)
    _git(d, "add", "-A", ts=1_700_000_000)
    _git(d, "commit", "-m", "add", ts=1_700_000_000)
    repo = GitRepo(d)
    return repo, repo.resolve("main")


def _episode(sha: str) -> Episode:
    return Episode(id="ep-0001", title="t", kind="change", commit_shas=[sha], paths=[], rationale="r")


def test_bundle_has_untrusted_notice(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    bundle, _, _ = render_bundle(repo, _episode(repo.resolve("main")))
    assert "untrusted" in bundle.lower()


def test_bundle_fence_outgrows_backticks_in_diff(tmp_path) -> None:
    # A diff whose content contains a ``` run must be wrapped in a longer fence,
    # so the injected backticks can't close the code block early.
    repo, sha = _one_commit_repo(tmp_path, "fence", "doc.md", "intro\n```\ncode\n```\n")
    bundle, _, _ = render_bundle(repo, _episode(sha))
    assert "````diff" in bundle  # a 4-backtick fence, not the default 3


def test_render_bundle_scrubs_planted_secret(tmp_path) -> None:
    repo, sha = _one_commit_repo(
        tmp_path, "secret", ".env", 'API_KEY="supersecretvalue12345"\n'
    )
    bundle, redactions, _ = render_bundle(repo, _episode(sha))
    assert redactions >= 1
    assert "supersecretvalue12345" not in bundle


class _FakeSource:
    """Stands in for GitHubSource; returns canned PRs and records calls."""

    def __init__(self, pulls):
        self._pulls = pulls
        self.calls: list[str] = []

    def pulls_for_commit(self, sha):
        self.calls.append(sha)
        return self._pulls


def test_bundle_enriched_with_pr_why(tmp_path) -> None:
    from repo_history.github import Issue, PullRequest

    repo, sha = _one_commit_repo(tmp_path, "enr", "a.py", "x = 1\n")
    pr = PullRequest(
        number=412,
        title="Move sessions server-side",
        body="JWT logout was impossible.",
        issues=(Issue(number=400, title="Cannot force logout", body="Users stay in."),),
        review_notes=("This breaks SSO.",),
    )
    bundle, _r, prs = render_bundle(repo, _episode(sha), _FakeSource([pr]))
    assert prs == [412]
    assert "Discussion (from PRs & issues)" in bundle
    assert "PR #412" in bundle
    assert "JWT logout was impossible." in bundle
    assert "Closes #400" in bundle
    assert "This breaks SSO." in bundle


def test_bundle_enrichment_scrubs_pr_text(tmp_path) -> None:
    from repo_history.github import PullRequest

    repo, sha = _one_commit_repo(tmp_path, "enrsec", "a.py", "x = 1\n")
    pr = PullRequest(number=1, title="t", body='set token = "supersecretvalue12345"')
    bundle, redactions, _ = render_bundle(repo, _episode(sha), _FakeSource([pr]))
    assert redactions >= 1
    assert "supersecretvalue12345" not in bundle


def test_bundle_without_source_has_no_discussion(fixture_repo: FixtureRepo) -> None:
    repo = fixture_repo.repo
    bundle, _r, prs = render_bundle(repo, _episode(repo.resolve("main")))
    assert prs == []
    assert "Discussion" not in bundle


def test_check_episode_id_rejects_traversal() -> None:
    for good in ["ep-0001", "release_1.2", "abc"]:
        _check_episode_id(good)  # no raise
    for bad in ["../etc/passwd", "..", ".", "a/b", "a\\b", "with space"]:
        with pytest.raises(ValueError):
            _check_episode_id(bad)


def test_materialize_rejects_unsafe_episode_id(fixture_repo: FixtureRepo, tmp_path) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    result.episodes[0].id = "../../escape"
    with pytest.raises(ValueError):
        materialize(fixture_repo.repo, result, tmp_path / ".repo-memory", ref="main")


def test_condense_diff_respects_total_cap() -> None:
    diff = "\n".join(
        f"diff --git a/f{i}.py b/f{i}.py\n+x" for i in range(1000)
    )
    condensed = condense_diff(diff, max_file_lines=10, max_total_lines=20)
    assert "diff truncated at 20 lines" in condensed


def test_materialize_writes_manifest_and_bundles(
    fixture_repo: FixtureRepo, tmp_path
) -> None:
    result = run_analysis(fixture_repo.repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialized = materialize(fixture_repo.repo, result, out, ref="main")

    manifest = json.loads((materialized.work_dir / "manifest.json").read_text())
    assert manifest["method"] == "mechanical"
    assert manifest["ref"] == "main"
    assert len(manifest["episodes"]) == materialized.episode_count

    # every referenced bundle exists on disk and names its episode
    for entry in manifest["episodes"]:
        bundle = (materialized.work_dir / entry["bundle"]).read_text()
        assert entry["id"] in bundle

    # the work dir is kept out of the user's commits
    assert (out / ".gitignore").read_text().strip() == f"{WORK_DIRNAME}/"


def test_materialize_scrubs_written_bundle(tmp_path) -> None:
    # End-to-end: a secret in a real commit must not appear in the file on disk.
    repo, _sha = _one_commit_repo(
        tmp_path, "msecret", ".env", 'DATABASE_URL=postgres://u:hunter2pass@h/db\n'
    )
    result = run_analysis(repo, "main", method="mechanical")
    out = tmp_path / ".repo-memory"
    materialized = materialize(repo, result, out, ref="main")

    assert materialized.redactions >= 1
    for bundle in (materialized.work_dir / "episodes").glob("*.md"):
        assert "hunter2pass" not in bundle.read_text()
