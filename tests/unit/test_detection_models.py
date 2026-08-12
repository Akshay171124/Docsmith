from __future__ import annotations

from src.detection.models import (
    ChangedSymbol,
    ChangeKind,
    DetectionResult,
    FileChange,
    InvestigationInput,
    InvestigationResult,
    Suspect,
    Verdict,
)


def test_changed_symbol_fields_and_hashable() -> None:
    symbol = ChangedSymbol(
        id="app.py::create_user",
        name="create_user",
        qualified_name="create_user",
        file="app.py",
        kind=ChangeKind.SIGNATURE_CHANGED,
        start_line=4,
        end_line=13,
        old_signature="def create_user(name)",
        new_signature="def create_user(name, email)",
    )
    assert symbol.id == "app.py::create_user"
    assert symbol.name == "create_user"
    assert symbol.qualified_name == "create_user"
    assert symbol.file == "app.py"
    assert symbol.kind == ChangeKind.SIGNATURE_CHANGED
    assert symbol.start_line == 4
    assert symbol.end_line == 13
    assert symbol.old_signature == "def create_user(name)"
    assert symbol.new_signature == "def create_user(name, email)"
    # frozen dataclass must be hashable
    assert symbol in {symbol}


def test_file_change_fields_with_none_old_content() -> None:
    fc = FileChange(
        path="app.py",
        old_content=None,
        new_content="def create_user(name, email): ...",
        changed_lines=frozenset({3, 4}),
    )
    assert fc.path == "app.py"
    assert fc.old_content is None
    assert fc.new_content == "def create_user(name, email): ..."
    assert fc.changed_lines == frozenset({3, 4})


def test_suspect_fields_and_hashable() -> None:
    suspect = Suspect(
        symbol_id="app.py::create_user",
        section_id="sec-001",
        change_kind=ChangeKind.REMOVED,
        via="name-reference",
    )
    assert suspect.symbol_id == "app.py::create_user"
    assert suspect.section_id == "sec-001"
    assert suspect.change_kind == ChangeKind.REMOVED
    assert suspect.via == "name-reference"
    # frozen dataclass must be hashable
    assert suspect in {suspect}


def test_detection_result_defaults() -> None:
    result = DetectionResult()
    assert result.changed_symbols == []
    assert result.suspects == []
    assert result.dropped == {}


def test_change_kind_members() -> None:
    members = {m.name for m in ChangeKind}
    assert members == {"ADDED", "REMOVED", "SIGNATURE_CHANGED", "BODY_CHANGED"}


def test_verdict_fields_and_hashable() -> None:
    verdict = Verdict(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        stale=True,
        confidence=0.9,
        reason="Doc still shows the old signature.",
        wrong_claims=("takes 1 arg",),
    )
    assert verdict.symbol_id == "app.py::create_user"
    assert verdict.section_id == "README.md#users"
    assert verdict.stale is True
    assert verdict.confidence == 0.9
    assert verdict.reason == "Doc still shows the old signature."
    assert verdict.wrong_claims == ("takes 1 arg",)
    # frozen dataclass must be hashable
    assert verdict in {verdict}


def test_investigation_input_fields_with_none_old_code() -> None:
    inv_input = InvestigationInput(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        change_kind=ChangeKind.ADDED,
        symbol_name="create_user",
        old_code=None,
        new_code="def create_user(name, email): ...",
        doc_section_text="## Users\nThis section describes user management.",
    )
    assert inv_input.symbol_id == "app.py::create_user"
    assert inv_input.section_id == "README.md#users"
    assert inv_input.change_kind == ChangeKind.ADDED
    assert inv_input.symbol_name == "create_user"
    assert inv_input.old_code is None
    assert inv_input.new_code == "def create_user(name, email): ..."
    assert inv_input.doc_section_text == "## Users\nThis section describes user management."
    # frozen dataclass must be hashable
    assert inv_input in {inv_input}


def test_investigation_result_defaults() -> None:
    result = InvestigationResult()
    assert result.verdicts == []
    assert result.skipped == {}
