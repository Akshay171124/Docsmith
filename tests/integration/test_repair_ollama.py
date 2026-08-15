"""Gated integration test against a real, locally running Ollama server.

Skipped by default (and always in CI, which has no Ollama installed). To run
it for real:

    ollama pull qwen2.5-coder:7b
    DOCSMITH_RUN_OLLAMA_TESTS=1 python3 -m pytest tests/integration/test_repair_ollama.py -v

The module must always be importable/collectable — the skip guard below never
touches the network at import time, so a plain `pytest` run (no env var set,
no Ollama running) collects this file and reports it as skipped, not errored.
"""

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

from src.detection.investigator import make_client
from src.detection.models import RepairRoute
from src.index.builder import build_index
from src.repair.engine import repair_pr
from src.utils.config import load_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_OLLAMA_TESTS") != "1",
    reason="set DOCSMITH_RUN_OLLAMA_TESTS=1 to run the real-Ollama repair test",
)

APP_BASE = "def create_user(name):\n    return {'name': name}\n"
APP_HEAD = "def create_user(name, email):\n    return {'name': name, 'email': email}\n"
README = "# Sample\n\n## Users\n\nUse `create_user(name)` to make a user.\n"


def _ollama_reachable(host: str) -> bool:
    """Best-effort check that a local Ollama server is up.

    Args:
        host: Base URL of the Ollama server (e.g. http://localhost:11434).

    Returns:
        True if a TCP connection to the server's host/port succeeds, else False.
    """
    parsed = urlparse(host)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 11434), timeout=1):
            return True
    except OSError:
        return False


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def test_real_ollama_repairs_signature_change(tmp_path):
    settings = load_settings("configs/base.yaml")
    if not _ollama_reachable(settings.ollama_host):
        pytest.skip("Ollama not reachable")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "app.py").write_text(APP_BASE)
    (repo / "README.md").write_text(README)
    base = _commit(repo, "base")
    (repo / "app.py").write_text(APP_HEAD)
    head = _commit(repo, "head")
    index_path = str(repo / ".docsmith" / "index.json")
    build_index(str(repo), output_path=index_path, embeddings=False, full=True)

    client = make_client(settings, backend_override="ollama")
    result = repair_pr(str(repo), base, head, index_path, settings, client)

    changed = [o for o in result.outcomes if o.proposal.changed]
    assert changed, "expected at least one changed repair proposal"
    assert any("email" in o.proposal.revised_text for o in changed)
    assert all(o.route in RepairRoute for o in result.outcomes)
