"""Tests for src/parsing/code_parser.parse_source — content-based symbol extraction."""

from __future__ import annotations

from src.parsing.code_parser import parse_source


class TestParseSource:
    """Tests for parse_source with in-memory content."""

    def test_str_input_python(self):
        """parse_source accepts a str and extracts a python function symbol."""
        symbols = parse_source("def foo():\n    pass\n", "x.py", "python")
        by_name = {s.name: s for s in symbols}
        assert "foo" in by_name
        sym = by_name["foo"]
        assert sym.id == "x.py::foo"
        assert sym.file == "x.py"
        assert sym.language == "python"

    def test_bytes_input_python(self):
        """parse_source accepts bytes and produces the same result as str input."""
        symbols = parse_source(b"def foo():\n    pass\n", "x.py", "python")
        by_name = {s.name: s for s in symbols}
        assert "foo" in by_name
        sym = by_name["foo"]
        assert sym.id == "x.py::foo"
        assert sym.file == "x.py"
        assert sym.language == "python"

    def test_typescript_snippet(self):
        """parse_source extracts a typescript function symbol."""
        symbols = parse_source("export function bar() {}\n", "y.ts", "typescript")
        by_name = {s.name: s for s in symbols}
        assert "bar" in by_name
        assert by_name["bar"].language == "typescript"
