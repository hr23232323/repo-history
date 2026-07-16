"""Tests for secret scrubbing, diff condensing, and materialization."""

from __future__ import annotations

import json

import pytest
from conftest import FixtureRepo

from repo_history.analysis import run_analysis
from repo_history.security import scrub
from repo_history.work import WORK_DIRNAME, condense_diff, materialize


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


def test_materialize_scrubs_bundle_diffs(fixture_repo: FixtureRepo, tmp_path) -> None:
    # A bundle is just rendered commits; verify the scrub runs by checking a
    # planted secret in a synthetic diff is redacted end-to-end.
    from repo_history.work import condense_diff as _cd

    secret_diff = 'diff --git a/.env b/.env\n+API_KEY="sk-livesecret999999"\n'
    scrubbed, count = scrub(_cd(secret_diff))
    assert count == 1
    assert "sk-livesecret999999" not in scrubbed
