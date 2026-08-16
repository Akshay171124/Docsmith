"""Gated integration test that runs the curated evaluation suite against a real,
locally running Ollama server.

Skipped by default (and always in CI, which has no Ollama installed). To run
it for real:

    ollama pull qwen2.5-coder:7b
    DOCSMITH_RUN_OLLAMA_TESTS=1 python3 -m pytest tests/integration/test_evaluate_ollama.py -v

The module must always be importable/collectable — the skip guard below never
touches the network at import time, so a plain `pytest` run (no env var set,
no Ollama running) collects this file and reports it as skipped, not errored.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

from evaluation.corpus import load_curated_cases
from evaluation.runner import run_suite
from src.detection.investigator import make_client
from src.index.embeddings import BgeSmallEmbedder
from src.utils.config import load_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_OLLAMA_TESTS") != "1",
    reason="set DOCSMITH_RUN_OLLAMA_TESTS=1 to run the real-Ollama evaluation test",
)


def _reachable(host: str) -> bool:
    """Best-effort check that a local Ollama server is up.

    Args:
        host: Base URL of the Ollama server (e.g. http://localhost:11434).

    Returns:
        True if a TCP connection to the server's host/port succeeds, else False.
    """
    p = urlparse(host)
    try:
        with socket.create_connection((p.hostname, p.port or 11434), timeout=1):
            return True
    except OSError:
        return False


def test_curated_eval_on_real_ollama():
    settings = load_settings("configs/base.yaml")
    if not _reachable(settings.ollama_host):
        pytest.skip("Ollama not reachable")
    cases = load_curated_cases()
    client = make_client(settings, backend_override="ollama")
    _, report = run_suite(
        cases,
        client,
        embedder=BgeSmallEmbedder(),
        repair=True,
        embeddings=True,
        suite="curated",
        backend="ollama",
        model=settings.ollama_model,
    )
    assert report.n_cases == len(cases)
    assert 0.0 <= report.precision <= 1.0
    assert 0.0 <= report.recall <= 1.0
