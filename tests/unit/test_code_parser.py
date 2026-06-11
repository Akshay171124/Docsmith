"""Tests for src/parsing/code_parser — Python symbol extraction via tree-sitter."""

from __future__ import annotations

from pathlib import Path

from src.parsing.code_parser import parse_file

FIXTURE = Path("tests/fixtures/sample_repo")


class TestParseFilePython:
    """Tests for parse_file on a Python fixture."""

    def test_symbol_names_superset(self):
        """parse_file returns symbols including create_user, UserService, and deactivate."""
        symbols = parse_file(str(FIXTURE / "app.py"))
        names = {s.name for s in symbols}
        assert {"create_user", "UserService", "deactivate"}.issubset(names)

    def test_create_user_symbol(self):
        """The create_user symbol has expected kind, signature, docstring, and language."""
        symbols = parse_file(str(FIXTURE / "app.py"))
        by_name = {s.name: s for s in symbols}
        sym = by_name["create_user"]

        assert sym.kind == "function"
        assert sym.signature.startswith("def create_user(")
        assert sym.docstring is not None
        assert "Create a user record" in sym.docstring
        assert sym.language == "python"
        assert sym.start_line == 4
        assert sym.end_line == 13
        assert sym.id == "tests/fixtures/sample_repo/app.py::create_user"

    def test_deactivate_qualified_name_and_kind(self):
        """The deactivate symbol has qualified_name UserService.deactivate and kind method."""
        symbols = parse_file(str(FIXTURE / "app.py"))
        matching = [s for s in symbols if s.qualified_name == "UserService.deactivate"]
        assert len(matching) == 1
        assert matching[0].kind == "method"

    def test_unsupported_extension_returns_empty(self):
        """parse_file returns [] for a file with an unsupported extension."""
        result = parse_file("some_file.txt")
        assert result == []
