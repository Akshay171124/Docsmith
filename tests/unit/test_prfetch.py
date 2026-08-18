import json
from unittest.mock import MagicMock

import pytest

import webapp.prfetch as prfetch
from webapp.prfetch import parse_pr_url


def test_parses_valid_pr_url():
    assert parse_pr_url("https://github.com/octo/repo/pull/42") == ("octo", "repo", 42)


def test_parses_with_trailing_slash():
    assert parse_pr_url("https://github.com/octo/repo/pull/42/") == ("octo", "repo", 42)


@pytest.mark.parametrize("bad", [
    "http://github.com/octo/repo/pull/42",       # not https
    "https://gitlab.com/octo/repo/pull/42",      # not github
    "https://github.com/octo/repo/issues/42",    # not a PR
    "https://github.com/octo/repo/pull/abc",     # non-numeric
    "https://github.com/octo/repo",              # no PR
    "not a url",
])
def test_rejects_bad_urls(bad):
    with pytest.raises(ValueError):
        parse_pr_url(bad)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


_PR_JSON = {
    "number": 7,
    "base": {
        "sha": "basesha",
        "repo": {
            "clone_url": "https://github.com/octo/repo.git",
            "size": 1000,
        },
    },
    "head": {
        "sha": "headsha",
        "repo": {"clone_url": "https://github.com/octo/repo.git"},
    },
}


def test_fetch_pr_clones_and_returns_shas(tmp_path, monkeypatch):
    monkeypatch.setattr(
        prfetch.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResponse(_PR_JSON),
    )
    calls = []

    def fake_run(cmd, **k):
        calls.append(cmd)
        return MagicMock()

    monkeypatch.setattr(prfetch.subprocess, "run", fake_run)

    repo, base, head = prfetch.fetch_pr("https://github.com/octo/repo/pull/7", str(tmp_path))

    assert base == "basesha" and head == "headsha"
    assert repo.endswith("repo")
    assert any(c[:2] == ["git", "clone"] for c in calls)               # cloned the base repo
    assert any("pull/7/head" in " ".join(c) for c in calls)            # fetched the PR head ref


def test_fetch_pr_rejects_oversized_repo(tmp_path, monkeypatch):
    big = json.loads(json.dumps(_PR_JSON))
    big["base"]["repo"]["size"] = prfetch.MAX_REPO_KB + 1
    monkeypatch.setattr(prfetch.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(big))
    with pytest.raises(ValueError, match="too large"):
        prfetch.fetch_pr("https://github.com/octo/repo/pull/7", str(tmp_path))
