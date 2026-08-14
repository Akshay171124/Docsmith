from src.detection.models import (
    ChangeKind,
    RepairInput,
    RepairOutcome,
    RepairProposal,
    RepairResult,
    RepairRoute,
    ValidationResult,
)


def test_repair_input_is_frozen_and_holds_fields():
    inp = RepairInput(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        file="app.py",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        symbol_name="create_user",
        new_code="def create_user(name, email): ...",
        section_text="Use create_user to make a user.",
        reason="signature changed",
        wrong_claims=("create_user(name)",),
        verdict_confidence=0.9,
    )
    assert inp.change_kind is ChangeKind.SIGNATURE_CHANGED
    assert inp.verdict_confidence == 0.9


def test_repair_route_values():
    assert RepairRoute.AUTOFIX.value == "autofix"
    assert RepairRoute.FLAG.value == "flag"
    assert RepairRoute.NO_CHANGE.value == "no_change"


def test_repair_outcome_and_result_defaults():
    proposal = RepairProposal(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        file="README.md",
        original_text="old",
        revised_text="new",
        diff="--- a\n+++ b\n-old\n+new",
        changed=True,
    )
    validation = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")
    outcome = RepairOutcome(
        proposal=proposal, validation=validation, route=RepairRoute.AUTOFIX, reason="ok"
    )
    result = RepairResult()
    result.outcomes.append(outcome)
    result.skipped["repair_error"] = 1
    assert result.outcomes[0].route is RepairRoute.AUTOFIX
    assert result.outcomes[0].validation.accurate is True
    assert result.skipped == {"repair_error": 1}
