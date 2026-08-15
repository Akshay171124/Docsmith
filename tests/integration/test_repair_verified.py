"""Integration test for RepairResult.verified counting non-stale verdicts."""

from __future__ import annotations

from src.detection.models import RepairRoute  # noqa: F401
from src.llm.client import FakeLLMClient
from src.repair.engine import repair_pr
from src.utils.config import Settings
from tests.integration.test_repair_pr import _setup_repo


def _fresh_verdict_client() -> FakeLLMClient:
    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": "unused"}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        # staleness verdict: NOT stale
        return {"stale": False, "confidence": 0.2, "reason": "still accurate", "wrong_claims": []}

    return FakeLLMClient(respond)


def test_repair_pr_counts_verified_not_stale(tmp_path):
    repo, base, head, index_path = _setup_repo(tmp_path)
    result = repair_pr(str(repo), base, head, index_path, Settings(), _fresh_verdict_client())
    assert result.verified == 1  # the one suspect section was judged accurate
    assert result.outcomes == []  # nothing stale → nothing to repair
