"""Integration tests for the investigate orchestrator and CLI subcommand."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

import docsmith
from src.detection.investigator import investigate_pr
from src.index.builder import build_index
from src.llm.client import FakeLLMClient
from src.utils.config import load_settings

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

STALE_VERDICT = {
    "stale": True,
    "confidence": 0.9,
    "reason": "signature changed",
    "wrong_claims": ["old signature"],
}


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


def test_investigate_pr_returns_verdict_for_changed_symbol(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_HEAD)
    head_sha = _commit(repo, "change create_user signature")

    index_path = repo / ".docsmith" / "index.json"
    build_index(str(repo), output_path=str(index_path), embeddings=False)

    settings = load_settings()
    client = FakeLLMClient(STALE_VERDICT)

    result = investigate_pr(str(repo), base_sha, head_sha, str(index_path), settings, client)

    readme_verdicts = [v for v in result.verdicts if v.section_id.startswith("README.md#")]
    assert readme_verdicts, f"expected a README verdict in {result.verdicts!r}"
    assert readme_verdicts[0].stale is True
    assert readme_verdicts[0].symbol_id.endswith("::create_user")


def test_investigate_cli_prints_stale_verdict(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_HEAD)
    head_sha = _commit(repo, "change create_user signature")

    index_path = repo / ".docsmith" / "index.json"
    build_index(str(repo), output_path=str(index_path), embeddings=False)

    result = subprocess.run(
        [
            sys.executable,
            "docsmith.py",
            "investigate",
            "--repo",
            str(repo),
            "--base",
            base_sha,
            "--head",
            head_sha,
            "--index",
            str(index_path),
            "--backend",
            "fake",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"CLI exited with {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "STALE" in result.stdout
    assert "README.md#" in result.stdout
    assert "create_user" in result.stdout


def test_investigate_cli_reports_backend_unavailable_and_exits_1(monkeypatch, capsys):
    error_message = (
        "Could not reach Ollama at http://localhost:11434 — start it or run "
        "`ollama pull qwen2.5-coder:7b`"
    )

    def fake_investigate_pr(*_args, **_kwargs):
        raise RuntimeError(error_message)

    monkeypatch.setattr(docsmith, "investigate_pr", fake_investigate_pr)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docsmith.py",
            "investigate",
            "--repo",
            "dummy-repo",
            "--base",
            "base-sha",
            "--head",
            "head-sha",
            "--index",
            "dummy-index.json",
            "--config",
            "configs/base.yaml",
            "--backend",
            "ollama",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        docsmith.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert error_message in captured.err
    assert captured.out == ""
