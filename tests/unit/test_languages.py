"""Tests for src/parsing/languages — language registry and symbol queries."""

from src.parsing.languages import SUPPORTED_LANGUAGES, SYMBOL_QUERIES, language_for_path


class TestLanguageForPath:
    """Tests for the language_for_path function."""

    def test_known_extensions_map_correctly(self):
        """Each supported extension maps to the expected language name."""
        assert language_for_path("a/b/app.py") == "python"
        assert language_for_path("service.ts") == "typescript"
        assert language_for_path("m.js") == "javascript"
        assert language_for_path("main.go") == "go"

    def test_tsx_and_jsx_extensions(self):
        """tsx maps to typescript and jsx maps to javascript."""
        assert language_for_path("App.tsx") == "typescript"
        assert language_for_path("Component.jsx") == "javascript"

    def test_unknown_extension_returns_none(self):
        """Unsupported extensions return None."""
        assert language_for_path("notes.txt") is None

    def test_no_extension_returns_none(self):
        """Files with no extension (e.g. Makefile) return None."""
        assert language_for_path("Makefile") is None


class TestSupportedLanguages:
    """Tests for the SUPPORTED_LANGUAGES constant."""

    def test_every_language_has_symbol_query(self):
        """Every language in SUPPORTED_LANGUAGES has a non-empty entry in SYMBOL_QUERIES."""
        for lang in SUPPORTED_LANGUAGES:
            assert lang in SYMBOL_QUERIES, f"No query for language: {lang}"
            assert SYMBOL_QUERIES[lang].strip(), f"Empty query for language: {lang}"
