"""Tests for src/detection/symbol_mapper.py."""

from __future__ import annotations

from src.detection.models import ChangeKind, FileChange
from src.detection.symbol_mapper import map_changes


def _find(symbols, qualified_name):
    return next(s for s in symbols if s.qualified_name == qualified_name)


def test_added_function():
    old_content = "def foo():\n    return 1\n"
    new_content = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
    fc = FileChange(
        path="m.py",
        old_content=old_content,
        new_content=new_content,
        changed_lines=frozenset({5, 6}),
    )

    result = map_changes([fc])

    assert len(result) == 1
    symbol = result[0]
    assert symbol.qualified_name == "bar"
    assert symbol.kind == ChangeKind.ADDED
    assert symbol.old_signature is None
    assert symbol.new_signature == "def bar():"
    assert symbol.id == "m.py::bar"


def test_removed_function():
    old_content = "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n"
    new_content = "def foo():\n    return 1\n"
    fc = FileChange(
        path="m.py",
        old_content=old_content,
        new_content=new_content,
        changed_lines=frozenset(),
    )

    result = map_changes([fc])

    assert len(result) == 1
    symbol = result[0]
    assert symbol.qualified_name == "bar"
    assert symbol.kind == ChangeKind.REMOVED
    assert symbol.new_signature is None
    assert symbol.old_signature == "def bar():"


def test_signature_change():
    old_content = "def foo():\n    return 1\n"
    new_content = "def foo(x):\n    return 1\n"
    fc = FileChange(
        path="m.py",
        old_content=old_content,
        new_content=new_content,
        changed_lines=frozenset({1}),
    )

    result = map_changes([fc])

    assert len(result) == 1
    symbol = result[0]
    assert symbol.qualified_name == "foo"
    assert symbol.kind == ChangeKind.SIGNATURE_CHANGED
    assert symbol.old_signature == "def foo():"
    assert symbol.new_signature == "def foo(x):"
    assert symbol.old_signature != symbol.new_signature
    assert symbol.id == "m.py::foo"


def test_body_change():
    old_content = "def foo():\n    return 1\n"
    new_content = "def foo():\n    return 2\n"
    fc = FileChange(
        path="m.py",
        old_content=old_content,
        new_content=new_content,
        changed_lines=frozenset({2}),
    )

    result = map_changes([fc])

    assert len(result) == 1
    symbol = result[0]
    assert symbol.qualified_name == "foo"
    assert symbol.kind == ChangeKind.BODY_CHANGED
    assert symbol.old_signature == "def foo():"
    assert symbol.new_signature == "def foo():"


def test_unchanged_symbol_omitted():
    old_content = "def foo():\n    return 1\n\n\ndef baz():\n    return 9\n"
    new_content = "def foo():\n    return 1\n\n\ndef baz():\n    return 10\n"
    fc = FileChange(
        path="m.py",
        old_content=old_content,
        new_content=new_content,
        changed_lines=frozenset({6}),
    )

    result = map_changes([fc])

    qualified_names = {s.qualified_name for s in result}
    assert "foo" not in qualified_names
    baz = _find(result, "baz")
    assert baz.kind == ChangeKind.BODY_CHANGED


def test_rename_is_removed_plus_added():
    old_content = "def old_name():\n    return 1\n"
    new_content = "def new_name():\n    return 1\n"
    fc = FileChange(
        path="m.py",
        old_content=old_content,
        new_content=new_content,
        changed_lines=frozenset({1}),
    )

    result = map_changes([fc])

    qualified_names = {s.qualified_name: s for s in result}
    assert set(qualified_names) == {"old_name", "new_name"}
    assert qualified_names["old_name"].kind == ChangeKind.REMOVED
    assert qualified_names["new_name"].kind == ChangeKind.ADDED


def test_results_are_deterministically_ordered():
    new_content = (
        "def zeta():\n"
        "    return 1\n"
        "\n\n"
        "def alpha():\n"
        "    return 2\n"
        "\n\n"
        "def mango():\n"
        "    return 3\n"
    )
    fc = FileChange(
        path="m.py",
        old_content=None,
        new_content=new_content,
        changed_lines=frozenset(range(1, new_content.count("\n") + 1)),
    )

    result = map_changes([fc])

    qualified_names = [cs.qualified_name for cs in result]
    assert qualified_names == sorted(cs.qualified_name for cs in result)
    assert qualified_names == ["alpha", "mango", "zeta"]


def test_md_file_skipped():
    fc = FileChange(
        path="README.md",
        old_content="# Title\n",
        new_content="# Title Updated\n",
        changed_lines=frozenset({1}),
    )

    result = map_changes([fc])

    assert result == []
