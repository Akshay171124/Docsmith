"""Integration tests for the detector orchestrator: real repo -> DetectionResult."""

from __future__ import annotations

import subprocess

from src.detection.detector import detect
from src.detection.models import ChangeKind
from src.index.builder import build_index
from src.utils.config import load_settings

APP_PY_BASE = """\
def create_user(name):
    \"\"\"Create a user.\"\"\"
    return {"name": name}


def helper():
    x = 1
    y = 2
    return x + y
"""

APP_PY_HEAD_SIGNATURE_ONLY = """\
def create_user(name, email):
    \"\"\"Create a user.\"\"\"
    return {"name": name}


def helper():
    x = 1
    y = 2
    return x + y
"""

APP_PY_HEAD_WITH_WHITESPACE_HELPER = """\
def create_user(name, email):
    \"\"\"Create a user.\"\"\"
    return {"name": name}


def helper():
    x = 1

    y = 2
    return x + y
"""

README_BASE = """\
# Sample App

Use `create_user` to create a user.
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
    (repo / "README.md").write_text(README_BASE)
    base_sha = _commit(repo, "initial commit")
    return repo, base_sha


def test_detect_finds_signature_change_suspect(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_HEAD_SIGNATURE_ONLY)
    head_sha = _commit(repo, "change create_user signature")

    index_path = repo / ".docsmith" / "index.json"
    build_index(str(repo), output_path=str(index_path), embeddings=False)

    result = detect(str(repo), base_sha, head_sha, str(index_path), load_settings())

    create_user_symbols = [s for s in result.changed_symbols if s.name == "create_user"]
    assert len(create_user_symbols) == 1
    assert create_user_symbols[0].kind == ChangeKind.SIGNATURE_CHANGED

    matching_suspects = [
        s
        for s in result.suspects
        if s.change_kind == ChangeKind.SIGNATURE_CHANGED and s.symbol_id.endswith("::create_user")
    ]
    assert matching_suspects, f"No signature-change suspect found in {result.suspects!r}"


def test_detect_drops_whitespace_only_change(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_HEAD_WITH_WHITESPACE_HELPER)
    head_sha = _commit(repo, "change create_user signature and touch helper whitespace")

    index_path = repo / ".docsmith" / "index.json"
    build_index(str(repo), output_path=str(index_path), embeddings=False)

    result = detect(str(repo), base_sha, head_sha, str(index_path), load_settings())

    assert not any(s.name == "helper" for s in result.changed_symbols)
    assert result.dropped.get("whitespace_only", 0) >= 1
