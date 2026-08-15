import json

import pytest

from src.github.context import load_pr_context


def _write_event(tmp_path, payload) -> str:
    p = tmp_path / "event.json"
    p.write_text(json.dumps(payload))
    return str(p)


def test_load_pr_context_from_event(tmp_path):
    event = _write_event(
        tmp_path,
        {
            "number": 7,
            "pull_request": {
                "base": {"sha": "base123", "ref": "main"},
                "head": {"sha": "head456", "ref": "feature-x"},
            },
        },
    )
    env = {"GITHUB_REPOSITORY": "octo/repo", "GITHUB_EVENT_PATH": event}
    ctx = load_pr_context(env)
    assert ctx.repo == "octo/repo"
    assert ctx.base_sha == "base123"
    assert ctx.head_sha == "head456"
    assert ctx.pr_number == 7
    assert ctx.head_ref == "feature-x"
    assert ctx.base_ref == "main"


def test_load_pr_context_rejects_non_pr_event(tmp_path):
    event = _write_event(tmp_path, {"pushed": True})
    env = {"GITHUB_REPOSITORY": "octo/repo", "GITHUB_EVENT_PATH": event}
    with pytest.raises(ValueError, match="pull_request"):
        load_pr_context(env)


def test_load_pr_context_requires_env(tmp_path):
    with pytest.raises(ValueError):
        load_pr_context({})
