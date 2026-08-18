"""Gated integration test against the real webapp analyze pipeline.

Skipped by default (and always in CI, which has no test PR or running Ollama
configured). To run it for real:

    export DOCSMITH_RUN_WEB_LIVE=1
    export DOCSMITH_WEB_TEST_PR=https://github.com/you/repo/pull/1
    python3 -m pytest tests/integration/test_webapp_live.py -v

The module must always be importable/collectable — the skip guard below never
touches the network (or the other env vars) at import time, so a plain `pytest` run
(no env var set) collects this file and reports it as skipped, not errored.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_WEB_LIVE") != "1",
    reason="set DOCSMITH_RUN_WEB_LIVE=1 (+ Ollama running) to run the live web-analyze test",
)


def test_analyze_real_pr_on_ollama():
    from webapp.service import analyze

    pr_url = os.environ["DOCSMITH_WEB_TEST_PR"]  # a small public PR that touches code+docs
    result = analyze(pr_url, "ollama", embeddings=False)
    assert "verified" in result.summary
    assert isinstance(result.results, list)
