"""Integration tests for the detect CLI subcommand."""

from __future__ import annotations

import pathlib
import subprocess
import sys

from src.index.builder import build_index

REPO_ROOT = pathlib.Path(__file__).parents[2]

APP_PY_BASE = """\
def create_user(name):
    \"\"\"Create a user.\"\"\"
    return {"name": name}
"""

APP_PY_HEAD = """\
def create_user(name, email):
    \"\"\"Create a user.\"\"\"
    return {"name": name}
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


def test_detect_cli_reports_suspect_doc_file(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_HEAD)
    head_sha = _commit(repo, "change create_user signature")

    index_path = repo / ".docsmith" / "index.json"
    build_index(str(repo), output_path=str(index_path), embeddings=False)

    result = subprocess.run(
        [
            sys.executable,
            "docsmith.py",
            "detect",
            "--repo",
            str(repo),
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--index",
            str(index_path),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"CLI exited with {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Detected" in result.stdout
    assert "README.md" in result.stdout
    assert "create_user" in result.stdout or "README.md#" in result.stdout
