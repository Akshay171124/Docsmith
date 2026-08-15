from src.detection.models import ChangeKind, RepairProposal, RepairRoute, ValidationResult
from src.repair.confidence_router import route
from src.utils.config import Settings

SETTINGS = Settings()  # defaults: threshold 0.8, autofix {signature_changed}
CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")


def _proposal(changed=True):
    return RepairProposal(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        file="README.md",
        original_text="old",
        revised_text="new" if changed else "old",
        diff="(d)" if changed else "",
        changed=changed,
    )


def test_no_change_when_proposal_unchanged():
    r, reason = route(_proposal(changed=False), None, ChangeKind.SIGNATURE_CHANGED, 0.99, SETTINGS)
    assert r is RepairRoute.NO_CHANGE


def test_autofix_when_clean_mechanical_and_confident():
    r, reason = route(_proposal(), CLEAN, ChangeKind.SIGNATURE_CHANGED, 0.9, SETTINGS)
    assert r is RepairRoute.AUTOFIX


def test_flag_when_validation_dirty():
    dirty = ValidationResult(accurate=True, preserved=False, style_ok=True, notes="dropped text")
    r, reason = route(_proposal(), dirty, ChangeKind.SIGNATURE_CHANGED, 0.9, SETTINGS)
    assert r is RepairRoute.FLAG
    assert "validation" in reason


def test_flag_when_change_kind_not_mechanical():
    for kind in (ChangeKind.ADDED, ChangeKind.REMOVED, ChangeKind.BODY_CHANGED):
        r, reason = route(_proposal(), CLEAN, kind, 0.9, SETTINGS)
        assert r is RepairRoute.FLAG


def test_flag_when_confidence_below_threshold():
    r, reason = route(_proposal(), CLEAN, ChangeKind.SIGNATURE_CHANGED, 0.5, SETTINGS)
    assert r is RepairRoute.FLAG
    assert "confidence" in reason


def test_autofix_set_is_config_driven():
    widened = Settings(repair_autofix_change_kinds=("signature_changed", "body_changed"))
    r, reason = route(_proposal(), CLEAN, ChangeKind.BODY_CHANGED, 0.9, widened)
    assert r is RepairRoute.AUTOFIX
