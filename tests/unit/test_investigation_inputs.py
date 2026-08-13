from __future__ import annotations

from src.detection.investigator import build_investigation_inputs
from src.detection.models import ChangeKind, FileChange, Suspect
from src.models import DocSection, Index


def _section(section_id: str, raw: str) -> DocSection:
    return DocSection(
        id=section_id,
        heading_path=("Usage",),
        file="README.md",
        raw=raw,
        start_line=1,
        end_line=1,
        referenced_symbols=(),
        referenced_config_keys=(),
    )


def test_signature_change_produces_investigation_input() -> None:
    file_change = FileChange(
        path="m.py",
        old_content="def foo(x):\n    return x\n",
        new_content="def foo(x, y):\n    return x + y\n",
        changed_lines=frozenset({1, 2}),
    )
    index = Index(sections={"README.md#u": _section("README.md#u", "Call foo(x).")})
    suspect = Suspect(
        symbol_id="m.py::foo",
        section_id="README.md#u",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="index-link",
    )

    result = build_investigation_inputs([suspect], [file_change], index)

    assert len(result) == 1
    inv = result[0]
    assert inv.symbol_id == "m.py::foo"
    assert inv.section_id == "README.md#u"
    assert inv.change_kind == ChangeKind.SIGNATURE_CHANGED
    assert inv.symbol_name == "foo"
    assert inv.old_code is not None and "def foo(x)" in inv.old_code
    assert inv.new_code is not None and "def foo(x, y)" in inv.new_code
    assert inv.doc_section_text == "Call foo(x)."


def test_removed_symbol_has_no_new_code() -> None:
    file_change = FileChange(
        path="m.py",
        old_content="def foo(x):\n    return x\n",
        new_content="def bar():\n    return None\n",
        changed_lines=frozenset({1, 2}),
    )
    index = Index(sections={"README.md#u": _section("README.md#u", "Call foo(x).")})
    suspect = Suspect(
        symbol_id="m.py::foo",
        section_id="README.md#u",
        change_kind=ChangeKind.REMOVED,
        via="index-link",
    )

    result = build_investigation_inputs([suspect], [file_change], index)

    assert len(result) == 1
    inv = result[0]
    assert inv.new_code is None
    assert inv.old_code is not None and "def foo(x)" in inv.old_code


def test_method_qualified_name_yields_unqualified_symbol_name() -> None:
    file_change = FileChange(
        path="m.py",
        old_content="class UserService:\n    def deactivate(self):\n        pass\n",
        new_content="class UserService:\n    def deactivate(self, reason):\n        pass\n",
        changed_lines=frozenset({2}),
    )
    index = Index(sections={"README.md#u": _section("README.md#u", "Deactivate a user.")})
    suspect = Suspect(
        symbol_id="m.py::UserService.deactivate",
        section_id="README.md#u",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="index-link",
    )

    result = build_investigation_inputs([suspect], [file_change], index)

    assert len(result) == 1
    assert result[0].symbol_name == "deactivate"


def test_missing_section_is_omitted() -> None:
    file_change = FileChange(
        path="m.py",
        old_content="def foo(x):\n    return x\n",
        new_content="def foo(x, y):\n    return x + y\n",
        changed_lines=frozenset({1}),
    )
    index = Index(sections={})
    suspect = Suspect(
        symbol_id="m.py::foo",
        section_id="README.md#missing",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="index-link",
    )

    result = build_investigation_inputs([suspect], [file_change], index)

    assert result == []


def test_duplicate_suspects_are_deduped() -> None:
    file_change = FileChange(
        path="m.py",
        old_content="def foo(x):\n    return x\n",
        new_content="def foo(x, y):\n    return x + y\n",
        changed_lines=frozenset({1}),
    )
    index = Index(sections={"README.md#u": _section("README.md#u", "Call foo(x).")})
    suspect = Suspect(
        symbol_id="m.py::foo",
        section_id="README.md#u",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="index-link",
    )
    other_via = Suspect(
        symbol_id="m.py::foo",
        section_id="README.md#u",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="name-reference",
    )

    result = build_investigation_inputs([suspect, other_via], [file_change], index)

    assert len(result) == 1
