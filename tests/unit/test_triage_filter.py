"""Unit tests for src/detection/triage_filter.py — the deterministic triage stage."""

from __future__ import annotations

from src.detection.models import ChangedSymbol, ChangeKind, FileChange
from src.detection.triage_filter import triage
from src.utils.config import Settings


def _settings(**overrides):
    defaults = dict(
        ignore_paths=[],
        doc_ignore=[],
        skip_comment_only=True,
        skip_whitespace_only=True,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _symbol(
    file="src/foo.py",
    kind=ChangeKind.BODY_CHANGED,
    start_line=1,
    end_line=3,
    name="foo",
):
    return ChangedSymbol(
        id=f"{file}::{name}",
        name=name,
        qualified_name=name,
        file=file,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        old_signature="def foo():",
        new_signature="def foo():",
    )


class TestIgnoredPath:
    def test_matching_glob_is_dropped(self):
        symbol = _symbol(file="tests/unit/test_foo.py")
        fc = FileChange(
            path="tests/unit/test_foo.py",
            old_content="",
            new_content="def foo():\n    pass\n",
            changed_lines=frozenset({2}),
        )
        settings = _settings(ignore_paths=["**/test_*.py"])

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == []
        assert dropped["ignored_path"] == 1


class TestWhitespaceOnly:
    def test_whitespace_only_span_is_dropped(self):
        new_content = "def foo():\n    \n    \n"
        symbol = _symbol(file="src/foo.py", start_line=2, end_line=3)
        fc = FileChange(
            path="src/foo.py",
            old_content="def foo():\n    pass\n",
            new_content=new_content,
            changed_lines=frozenset({2, 3}),
        )
        settings = _settings(skip_whitespace_only=True)

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == []
        assert dropped["whitespace_only"] == 1


class TestCommentOnly:
    def test_comment_only_span_is_dropped(self):
        new_content = "def foo():\n    # a comment\n    # another comment\n"
        symbol = _symbol(file="src/foo.py", start_line=2, end_line=3)
        fc = FileChange(
            path="src/foo.py",
            old_content="def foo():\n    pass\n    pass\n",
            new_content=new_content,
            changed_lines=frozenset({2, 3}),
        )
        settings = _settings(skip_comment_only=True)

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == []
        assert dropped["comment_only"] == 1

    def test_disabled_setting_keeps_symbol(self):
        new_content = "def foo():\n    # a comment\n    # another comment\n"
        symbol = _symbol(file="src/foo.py", start_line=2, end_line=3)
        fc = FileChange(
            path="src/foo.py",
            old_content="def foo():\n    pass\n    pass\n",
            new_content=new_content,
            changed_lines=frozenset({2, 3}),
        )
        settings = _settings(skip_comment_only=False)

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == [symbol]
        assert dropped == {}


class TestKept:
    def test_real_code_change_is_kept(self):
        new_content = "def foo():\n    return 2\n"
        symbol = _symbol(file="src/foo.py", start_line=1, end_line=2)
        fc = FileChange(
            path="src/foo.py",
            old_content="def foo():\n    return 1\n",
            new_content=new_content,
            changed_lines=frozenset({2}),
        )
        settings = _settings()

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == [symbol]
        assert dropped == {}


class TestNonBodyKindsAlwaysKept:
    def test_added_symbol_kept_even_if_span_is_whitespace(self):
        new_content = "def foo():\n    \n    \n"
        symbol = _symbol(file="src/foo.py", kind=ChangeKind.ADDED, start_line=2, end_line=3)
        fc = FileChange(
            path="src/foo.py",
            old_content=None,
            new_content=new_content,
            changed_lines=frozenset({2, 3}),
        )
        settings = _settings()

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == [symbol]
        assert dropped == {}

    def test_body_changed_with_no_in_span_lines_is_kept(self):
        symbol = ChangedSymbol(
            id="m.py::foo",
            name="foo",
            qualified_name="foo",
            file="m.py",
            kind=ChangeKind.BODY_CHANGED,
            start_line=2,
            end_line=4,
            old_signature="def foo():",
            new_signature="def foo():",
        )
        fc = FileChange(
            path="m.py",
            old_content="a\nb\nc\n",
            new_content="a\nb\nc\nd\n",
            changed_lines=frozenset({10, 11}),
        )
        settings = _settings()

        kept, dropped = triage([symbol], [fc], settings)

        assert kept == [symbol]
        assert dropped == {}
