"""Tests for GitHub PR/issue enrichment. Network is stubbed; parsing is real."""

from __future__ import annotations

import subprocess

import pytest
from conftest import _git

from repo_history.github import GitHubSource, github_slug, parse_pulls


def _graphql(nodes: list[dict]) -> dict:
    return {"repository": {"object": {"associatedPullRequests": {"nodes": nodes}}}}


def test_parse_pulls_extracts_why_and_filters_bots() -> None:
    data = _graphql(
        [
            {
                "number": 412,
                "title": "Move sessions server-side",
                "bodyText": "JWT logout was impossible; switch to server sessions.",
                "closingIssuesReferences": {
                    "nodes": [{"number": 400, "title": "Cannot force logout", "bodyText": "Users stay logged in."}]
                },
                "reviews": {
                    "nodes": [
                        {"author": {"login": "alice"}, "state": "CHANGES_REQUESTED", "bodyText": "This breaks SSO."},
                        {"author": {"login": "copilot-pull-request-reviewer"}, "state": "COMMENTED", "bodyText": "nit"},
                        {"author": {"login": "bob"}, "state": "APPROVED", "bodyText": ""},
                    ]
                },
            }
        ]
    )
    pulls = parse_pulls(data)
    assert len(pulls) == 1
    pr = pulls[0]
    assert pr.number == 412
    assert "server sessions" in pr.body
    assert pr.issues[0].number == 400 and "logged in" in pr.issues[0].body
    # only the substantive human review survives (bot + empty dropped)
    assert pr.review_notes == ("This breaks SSO.",)


def test_parse_pulls_handles_no_association() -> None:
    assert parse_pulls(_graphql([])) == []
    assert parse_pulls({}) == []
    assert parse_pulls({"repository": {"object": None}}) == []


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/hr23232323/repo-history.git", ("hr23232323", "repo-history")),
        ("https://github.com/hr23232323/repo-history", ("hr23232323", "repo-history")),
        ("git@github.com:acme/Widget.git", ("acme", "Widget")),
        ("https://gitlab.com/acme/widget.git", None),
    ],
)
def test_github_slug(tmp_path, url, expected) -> None:
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-b", "main", ts=1_700_000_000)
    subprocess.run(["git", "remote", "add", "origin", url], cwd=d, check=True)
    assert github_slug(d) == expected


def test_github_slug_no_remote(tmp_path) -> None:
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-b", "main", ts=1_700_000_000)
    assert github_slug(d) is None


def test_source_uses_cache_and_injected_runner(tmp_path) -> None:
    calls = {"n": 0}

    def runner(query: str, variables: dict) -> dict:
        calls["n"] += 1
        return _graphql([{"number": 1, "title": "t", "bodyText": "why"}])

    cache = tmp_path / "cache"
    src = GitHubSource("o", "r", runner=runner, cache_dir=cache)

    first = src.pulls_for_commit("deadbeef")
    second = src.pulls_for_commit("deadbeef")  # served from cache, no 2nd call
    assert first == second
    assert first[0].body == "why"
    assert calls["n"] == 1
    assert (cache / "deadbeef.json").exists()


def test_source_degrades_on_network_error(tmp_path) -> None:
    def boom(query: str, variables: dict) -> dict:
        raise RuntimeError("gh exploded")

    src = GitHubSource("o", "r", runner=boom, cache_dir=tmp_path)
    assert src.pulls_for_commit("sha") == []  # error -> empty, never raises
