"""Integration tests for the repair_pr orchestrator."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.detection.models import RepairRoute
from src.index.builder import build_index
from src.llm.client import FakeLLMClient
from src.repair.engine import repair_pr
from src.utils.config import Settings

APP_BASE = "def create_user(name):\n    return {'name': name}\n"
APP_HEAD = "def create_user(name, email):\n    return {'name': name, 'email': email}\n"
README = "# Sample\n\n## Users\n\nUse `create_user` to make a user.\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _fake_pipeline_client() -> FakeLLMClient:
    corrected = "Use `create_user(name, email)` to make a user."

    def respond(user: str) -> dict:
        if "Rewrite" in user:  # repair call
            return {"revised_text": corrected}
        if "proposed revision" in user:  # validate call
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        # staleness verdict call
        return {
            "stale": True,
            "confidence": 0.9,
            "reason": "create_user now takes an email argument",
            "wrong_claims": ["create_user(name)"],
        }

    return FakeLLMClient(respond)


def _setup_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text(APP_BASE)
    (repo / "README.md").write_text(README)
    base = _commit_all(repo, "base")
    (repo / "app.py").write_text(APP_HEAD)
    head = _commit_all(repo, "head")
    index_path = str(repo / ".docsmith" / "index.json")
    build_index(str(repo), output_path=index_path, embeddings=False, full=True)
    return repo, base, head, index_path


def test_repair_pr_autofixes_signature_change(tmp_path):
    repo, base, head, index_path = _setup_repo(tmp_path)
    result = repair_pr(str(repo), base, head, index_path, Settings(), _fake_pipeline_client())
    autofixes = [o for o in result.outcomes if o.route is RepairRoute.AUTOFIX]
    assert len(autofixes) == 1
    outcome = autofixes[0]
    assert outcome.proposal.section_id == "README.md#users"
    assert "create_user(name, email)" in outcome.proposal.revised_text
    assert "+Use `create_user(name, email)` to make a user." in outcome.proposal.diff
    assert outcome.validation is not None and outcome.validation.accurate is True
