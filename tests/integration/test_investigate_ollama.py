"""Gated integration test against a real, locally running Ollama server.

Skipped by default (and always in CI, which has no Ollama installed). To run
it for real:

    ollama pull qwen2.5-coder:7b
    DOCSMITH_RUN_OLLAMA_TESTS=1 python3 -m pytest tests/integration/test_investigate_ollama.py -v

The module must always be importable/collectable — the skip guard below never
touches the network at import time, so a plain `pytest` run (no env var set,
no Ollama running) collects this file and reports it as skipped, not errored.
"""

from __future__ import annotations

import os
import subprocess
import urllib.error
import urllib.request

import pytest

from src.detection.investigator import investigate_pr
from src.index.builder import build_index
from src.llm.client import OllamaClient
from src.utils.config import load_settings

APP_PY_BASE = """\
def create_user(name: str, email: str) -> dict:
    \"\"\"Create a user record.\"\"\"
    return {"name": name, "email": email}


class UserService:
    \"\"\"Manages user lifecycle.\"\"\"

    def deactivate(self, user_id: int) -> bool:
        \"\"\"Deactivate a user by id.\"\"\"
        return True
"""

APP_PY_HEAD = """\
def create_user(name: str, email: str, role: str = "member") -> dict:
    \"\"\"Create a user record with a role.\"\"\"
    return {"name": name, "email": email, "role": role}


class UserService:
    \"\"\"Manages user lifecycle.\"\"\"

    def deactivate(self, user_id: int) -> bool:
        \"\"\"Deactivate a user by id.\"\"\"
        return True
"""

README = """\
# Sample App

## Users

Use `create_user` to make a user. The `UserService` class manages lifecycle;
call `deactivate` to disable an account.

## Formatting

`formatName` joins a first and last name.

## Config

Set the `MAX_USERS` environment variable to cap account creation.
"""


def _run_git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo, message):
    _run_git(repo, "add", "-A")
    _run_git(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-m",
        message,
    )
    return _run_git(repo, "rev-parse", "HEAD")


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    (repo / "app.py").write_text(APP_PY_BASE)
    (repo / "README.md").write_text(README)
    base_sha = _commit(repo, "initial commit")
    return repo, base_sha


def _ollama_reachable(host: str) -> bool:
    """Best-effort check that a local Ollama server is up.

    Args:
        host: Base URL of the Ollama server (e.g. http://localhost:11434).

    Returns:
        True if the server responded to a quick /api/tags request, else False.
    """
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=1) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_OLLAMA_TESTS") != "1",
    reason="set DOCSMITH_RUN_OLLAMA_TESTS=1 to run the real-Ollama integration test",
)


def test_investigate_pr_with_real_ollama_flags_stale_section(tmp_path):
    settings = load_settings()

    if not _ollama_reachable(settings.ollama_host):
        pytest.skip(f"Ollama not reachable at {settings.ollama_host}")

    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_HEAD)
    head_sha = _commit(repo, "add role parameter to create_user")

    index_path = repo / ".docsmith" / "index.json"
    build_index(str(repo), output_path=str(index_path), embeddings=False)

    client = OllamaClient(settings.ollama_model, settings.ollama_host)
    result = investigate_pr(str(repo), base_sha, head_sha, str(index_path), settings, client)

    users_verdicts = [v for v in result.verdicts if v.section_id == "README.md#users"]
    assert users_verdicts, f"expected a README.md#users verdict in {result.verdicts!r}"
    assert any(v.stale is True for v in users_verdicts), users_verdicts

    stale_section_ids = {v.section_id for v in result.verdicts if v.stale is True}
    assert "README.md#formatting" not in stale_section_ids
    assert "README.md#config" not in stale_section_ids
