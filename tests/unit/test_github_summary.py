from src.detection.models import (
    RepairOutcome,
    RepairProposal,
    RepairResult,
    RepairRoute,
    ValidationResult,
)
from src.github.summary import MARKER, build_summary

CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")


def _outcome(route, sid, diff="", reason="because"):
    proposal = RepairProposal(
        symbol_id="app.py::f", section_id=sid, file="README.md",
        original_text="old", revised_text="new", diff=diff, changed=True,
    )
    return RepairOutcome(proposal=proposal, validation=CLEAN, route=route, reason=reason)


def test_summary_has_marker_headline_and_sections():
    result = RepairResult(
        outcomes=[
            _outcome(RepairRoute.AUTOFIX, "README.md#users", reason="signature_changed"),
            _outcome(
                RepairRoute.FLAG, "README.md#config", diff="-old\n+new", reason="body_changed"
            ),
        ],
        verified=3,
    )
    body = build_summary(result, "https://github.com/o/r/pull/42", auto_fix=True)
    assert body.startswith(MARKER)
    assert "3 verified" in body
    assert "1 auto-fixed" in body
    assert "https://github.com/o/r/pull/42" in body
    assert "1 flagged" in body
    assert "README.md#users" in body
    assert "README.md#config" in body
    assert "<details>" in body and "```diff" in body and "-old" in body
    assert "merge" not in body.lower() or "never" in body.lower()  # never implies auto-merge


def test_summary_autofix_disabled_labels_proposed():
    result = RepairResult(outcomes=[_outcome(RepairRoute.AUTOFIX, "README.md#x")], verified=0)
    body = build_summary(result, None, auto_fix=False)
    assert "Proposed" in body            # not opened as a PR
    assert "0 verified" in body
