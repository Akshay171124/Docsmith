"""Multi-language symbol extraction tests for TypeScript, JavaScript, and Go."""

from pathlib import Path

from src.parsing.code_parser import parse_file

FIXTURE = Path("tests/fixtures/sample_repo")


class TestTypeScript:
    def test_extracts_function(self):
        symbols = parse_file(str(FIXTURE / "service.ts"))
        names = [s.name for s in symbols]
        assert "formatName" in names

    def test_function_language(self):
        symbols = parse_file(str(FIXTURE / "service.ts"))
        by_name = {s.name: s for s in symbols}
        assert by_name["formatName"].language == "typescript"

    def test_extracts_class(self):
        symbols = parse_file(str(FIXTURE / "service.ts"))
        by_name = {s.name: s for s in symbols}
        assert "Cache" in by_name
        assert by_name["Cache"].kind == "class"


class TestJavaScript:
    def test_extracts_function(self):
        symbols = parse_file(str(FIXTURE / "widget.js"))
        names = [s.name for s in symbols]
        assert "renderWidget" in names

    def test_extracts_class(self):
        symbols = parse_file(str(FIXTURE / "widget.js"))
        by_name = {s.name: s for s in symbols}
        assert "Widget" in by_name
        assert by_name["Widget"].kind == "class"

    def test_language(self):
        symbols = parse_file(str(FIXTURE / "widget.js"))
        assert all(s.language == "javascript" for s in symbols)


class TestGo:
    def test_extracts_function(self):
        symbols = parse_file(str(FIXTURE / "cache.go"))
        names = [s.name for s in symbols]
        assert "Add" in names

    def test_extracts_struct_as_class(self):
        symbols = parse_file(str(FIXTURE / "cache.go"))
        by_name = {s.name: s for s in symbols}
        assert "Store" in by_name
        assert by_name["Store"].kind == "class"

    def test_language(self):
        symbols = parse_file(str(FIXTURE / "cache.go"))
        assert all(s.language == "go" for s in symbols)


class TestUnsupported:
    def test_markdown_returns_empty(self):
        result = parse_file(str(FIXTURE / "README.md"))
        assert result == []
