from __future__ import annotations

from src.detection.models import (
    ChangedSymbol,
    ChangeKind,
    DetectionResult,
    FileChange,
    Suspect,
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
