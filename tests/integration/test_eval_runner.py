"""Integration tests for the evaluation runner: replay cases and score them."""

from __future__ import annotations

from evaluation.models import Case, Gold
from evaluation.runner import evaluate_cases, run_suite
from src.index.embeddings import FakeEmbedder
from src.llm.client import FakeLLMClient

POSITIVE = Case(
    case_id="pos",
    base_files={
        "app.py": "def create_user(name):\n    return {\"name\": name}\n",
        "README.md": "# App\n\n## Users\n\nCall `create_user` with a name.\n",
    },
    head_files={
        "app.py": "def create_user(name, email):\n    return {\"name\": name, \"email\": email}\n",
        "README.md": "# App\n\n## Users\n\nCall `create_user` with a name.\n",
    },
    gold=Gold(
        stale_section_ids=frozenset({"README.md#users"}),
        fixes={"README.md#users": "Call `create_user` with a name and email."},
    ),
)


def _stale_client() -> FakeLLMClient:
    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": "Call `create_user` with a name and email."}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        return {
            "stale": True,
            "confidence": 0.9,
            "reason": "signature changed",
            "wrong_claims": ["create_user"],
        }

    return FakeLLMClient(respond)


def _malformed_repair_client() -> FakeLLMClient:
    """Correctly flags the section stale but returns an unusable repair reply."""

    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"not_revised_text": "oops"}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        return {
            "stale": True,
            "confidence": 0.9,
            "reason": "signature changed",
            "wrong_claims": ["create_user"],
        }

    return FakeLLMClient(respond)


def test_malformed_repair_does_not_cost_detection_credit():
    """A section correctly flagged stale must stay a detection hit even if repair fails.

    Regression test: repair_pr silently drops outcomes whose repair reply is
    malformed, so deriving `flagged` from repair outcomes (instead of from the
    investigation verdicts) would wrongly turn this into a false negative.
    """
    results = evaluate_cases(
        [POSITIVE],
        _malformed_repair_client(),
        embedder=FakeEmbedder(),
        repair=True,
        embeddings=False,
    )
    assert len(results) == 1
    assert (results[0].tp, results[0].fn) == (1, 0)
    assert results[0].corrections == ()


def test_runner_scores_positive_case(tmp_path):
    results = evaluate_cases(
        [POSITIVE], _stale_client(), embedder=FakeEmbedder(), repair=True, embeddings=False
    )
    assert len(results) == 1
    assert (results[0].tp, results[0].fp, results[0].fn) == (1, 0, 0)
    assert len(results[0].corrections) == 1
    assert results[0].corrections[0]["exact"] is True  # fake rewrite == gold fix


def test_run_suite_aggregates():
    _, report = run_suite(
        [POSITIVE],
        _stale_client(),
        embedder=FakeEmbedder(),
        repair=True,
        embeddings=False,
        suite="curated",
        backend="fake",
        model="none",
    )
    assert report.precision == 1.0 and report.recall == 1.0 and report.f1 == 1.0
    assert report.n_cases == 1
