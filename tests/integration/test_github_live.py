"""Gated integration test against a real GitHub pull request.

Skipped by default (and always in CI, which has no test PR/token configured). To run
it for real:

    export DOCSMITH_RUN_GITHUB_TESTS=1
    export DOCSMITH_GITHUB_TEST_REPO=you/docsmith-sandbox
    export DOCSMITH_GITHUB_TEST_PR=1
    export GITHUB_TOKEN=...
    python3 -m pytest tests/integration/test_github_live.py -v

The module must always be importable/collectable — the skip guard below never
touches the network (or the other env vars) at import time, so a plain `pytest` run
(no env var set) collects this file and reports it as skipped, not errored.
"""

import os

import pytest

from src.github.client import PyGithubClient
from src.github.summary import MARKER

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_GITHUB_TESTS") != "1",
    reason="set DOCSMITH_RUN_GITHUB_TESTS=1 (with a token + test repo) to run the live GitHub test",
)


def test_upsert_summary_comment_on_real_pr():
    repo = os.environ["DOCSMITH_GITHUB_TEST_REPO"]  # e.g. "you/docsmith-sandbox"
    pr_number = int(os.environ["DOCSMITH_GITHUB_TEST_PR"])
    token = os.environ["GITHUB_TOKEN"]
    client = PyGithubClient(repo, token)
    client.upsert_summary_comment(pr_number, f"{MARKER}\nDocsmith live test — safe to delete.")
    # A second upsert must not create a duplicate (idempotency); no exception == pass.
    client.upsert_summary_comment(pr_number, f"{MARKER}\nDocsmith live test — updated.")
