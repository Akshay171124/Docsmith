"""Integration tests for build_index — full repo walk producing an Index."""

from __future__ import annotations

import pathlib

from src.index.builder import build_index
from src.parsing.languages import language_for_path

FIXTURE_REPO = "tests/fixtures/sample_repo"


def test_build_index_symbols_and_sections() -> None:
    """build_index collects expected symbols and the Users section, and links them."""
    index = build_index(FIXTURE_REPO)

    symbol_names = {sym.name for sym in index.symbols.values()}
    expected_symbols = {"create_user", "UserService", "deactivate", "formatName", "Cache"}
    assert expected_symbols.issubset(symbol_names)

    heading_paths = {sec.heading_path for sec in index.sections.values()}
    assert ("Users",) in heading_paths

    users_section_ids = {
        sec_id
        for sec_id, sec in index.sections.items()
        if sec.heading_path == ("Users",)
    }
    linked_symbol_names = {
        index.symbols[link.symbol_id].name
        for link in index.links
        if link.section_id in users_section_ids and link.symbol_id in index.symbols
    }
    assert {"create_user", "UserService", "deactivate"}.issubset(linked_symbol_names)


def test_indexed_symbols_have_supported_language() -> None:
    """Every symbol's source file maps to a supported language."""
    index = build_index(FIXTURE_REPO)
    for sym in index.symbols.values():
        assert language_for_path(sym.file) is not None, (
            f"Symbol {sym.id!r} from unsupported file {sym.file!r}"
        )


def test_build_index_writes_output_file(tmp_path: pathlib.Path) -> None:
    """build_index writes index.json when output_path is given and returns a non-empty Index."""
    output = tmp_path / "index.json"
    index = build_index(FIXTURE_REPO, output_path=str(output))

    assert output.exists(), "index.json was not written"
    assert index.symbols or index.sections, "Returned index is empty"
