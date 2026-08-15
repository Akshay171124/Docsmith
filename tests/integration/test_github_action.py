"""Integration tests for the GitHub Action entrypoint (env -> settings -> report)."""

from __future__ import annotations

import json

from src.github.action import run_action
from src.github.client import FakeGitHubClient
from src.github.summary import MARKER
from src.llm.client import FakeLLMClient
from tests.integration.test_repair_pr import _setup_repo


def _pipeline_client() -> FakeLLMClient:
    corrected = "Use `create_user(name, email)` to make a user."

    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": corrected}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        return {
            "stale": True, "confidence": 0.9,
            "reason": "create_user now takes an email argument",
            "wrong_claims": ["create_user(name)"],
        }

    return FakeLLMClient(respond)


def _event(tmp_path, base_sha, head_sha) -> str:
    payload = {
        "number": 7,
        "pull_request": {
            "base": {"sha": base_sha, "ref": "main"},
            "head": {"sha": head_sha, "ref": "feature"},
        },
    }
    p = tmp_path / "event.json"
    p.write_text(json.dumps(payload))
    return str(p)


def test_run_action_reports_autofix(tmp_path):
    repo, base, head, _index_path = _setup_repo(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "octo/repo",
        "GITHUB_EVENT_PATH": _event(tmp_path, base, head),
        "INPUT_LLM-BACKEND": "fake",
    }
    gh = FakeGitHubClient(fix_pr_url="https://github.com/octo/repo/pull/50")
    counts = run_action(
        env, str(repo), embeddings=False, llm_client=_pipeline_client(), gh_client=gh
    )
    assert counts.fixed == 1
    assert counts.fix_pr_url == "https://github.com/octo/repo/pull/50"
    assert gh.fix_prs[0]["branch"] == "docsmith/fix-pr-7"
    assert "create_user(name, email)" in gh.fix_prs[0]["files"]["README.md"]
    assert MARKER in gh.comments[7] and "auto-fixed" in gh.comments[7]


def test_github_action_cli_writes_outputs(tmp_path, monkeypatch):
    import docsmith
    from src.github.reporter import ReportCounts

    out = tmp_path / "gh_output"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(
        docsmith, "run_action",
        lambda env, repo: ReportCounts(verified=2, fixed=1, flagged=3, fix_pr_url="u"),
    )
    monkeypatch.setattr("sys.argv", ["docsmith", "github-action", "--repo", str(tmp_path)])
    docsmith.main()
    text = out.read_text()
    assert "verified=2" in text and "fixed=1" in text and "flagged=3" in text
    assert "fix-pr-url=u" in text
