from src.detection.models import RepairOutcome, RepairProposal, RepairRoute, ValidationResult
from src.github.apply import apply_corrections
from src.models import DocSection, Index

CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")


def _section(sid, start, end):
    return DocSection(
        id=sid, heading_path=("H",), file="README.md", raw="x",
        start_line=start, end_line=end, referenced_symbols=(), referenced_config_keys=(),
    )


def _autofix(sid, revised):
    proposal = RepairProposal(
        symbol_id="app.py::f", section_id=sid, file="README.md",
        original_text="old", revised_text=revised, diff="(d)", changed=True,
    )
    return RepairOutcome(
        proposal=proposal, validation=CLEAN, route=RepairRoute.AUTOFIX, reason="ok"
    )


def test_apply_replaces_section_span():
    index = Index(sections={"README.md#a": _section("README.md#a", 2, 2)})
    original = "line1\nOLD\nline3\n"
    files = apply_corrections([_autofix("README.md#a", "NEW")], index, lambda p: original)
    assert files == {"README.md": "line1\nNEW\nline3\n"}


def test_apply_multiple_edits_bottom_up_no_drift():
    index = Index(
        sections={
            "README.md#a": _section("README.md#a", 1, 1),
            "README.md#b": _section("README.md#b", 3, 3),
        }
    )
    original = "A\nmid\nB\n"
    outcomes = [_autofix("README.md#a", "A2\nA3"), _autofix("README.md#b", "B2")]
    files = apply_corrections(outcomes, index, lambda p: original)
    # #b (line 3) applied first, then #a (line 1); no line drift
    assert files == {"README.md": "A2\nA3\nmid\nB2\n"}


def test_apply_ignores_non_autofix_and_missing_sections():
    index = Index(sections={})
    files = apply_corrections([_autofix("README.md#gone", "NEW")], index, lambda p: "x\n")
    assert files == {}
