"""Integration tests for build_index — full repo walk producing an Index."""

from __future__ import annotations

import json
import pathlib

from src.index.builder import build_index
from src.parsing.languages import language_for_path

FIXTURE_REPO = "tests/fixtures/sample_repo"


def test_build_index_symbols_and_sections() -> None:
    """build_index collects expected symbols and the Users section, and links them."""
    index = build_index(FIXTURE_REPO, embeddings=False)

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
    index = build_index(FIXTURE_REPO, embeddings=False)
    for sym in index.symbols.values():
        assert language_for_path(sym.file) is not None, (
            f"Symbol {sym.id!r} from unsupported file {sym.file!r}"
        )


def test_build_index_writes_output_file(tmp_path: pathlib.Path) -> None:
    """build_index writes index.json when output_path is given and returns a non-empty Index."""
    output = tmp_path / "index.json"
    index = build_index(FIXTURE_REPO, output_path=str(output), embeddings=False)

    assert output.exists(), "index.json was not written"
    assert index.symbols or index.sections, "Returned index is empty"


def test_symbol_id_collision_both_survive(tmp_path: pathlib.Path) -> None:
    """Two top-level functions with the same name both survive with distinct ids."""
    py_file = tmp_path / "dup.py"
    py_file.write_text("def foo(): pass\n\ndef foo(): pass\n")

    index = build_index(str(tmp_path), embeddings=False)

    foo_symbols = [s for s in index.symbols.values() if s.name == "foo"]
    assert len(foo_symbols) == 2, (
        f"Expected 2 symbols named 'foo', got {len(foo_symbols)}: "
        f"{[s.id for s in foo_symbols]}"
    )
    ids = [s.id for s in foo_symbols]
    assert ids[0] != ids[1], f"Both 'foo' symbols share the same id: {ids[0]!r}"

    # Every stored key must equal the item's own .id field.
    for key, sym in index.symbols.items():
        assert key == sym.id, f"Key {key!r} != symbol.id {sym.id!r}"


def test_duplicate_heading_sections_both_survive(tmp_path: pathlib.Path) -> None:
    """Two ## Examples headings in one .md file both survive with distinct ids."""
    md_file = tmp_path / "guide.md"
    md_file.write_text(
        "## Examples\n\nFirst example body.\n\n## Examples\n\nSecond example body.\n"
    )

    index = build_index(str(tmp_path), embeddings=False)

    examples_sections = [
        s for s in index.sections.values() if s.heading_path == ("Examples",)
    ]
    assert len(examples_sections) == 2, (
        f"Expected 2 sections with heading_path ('Examples',), "
        f"got {len(examples_sections)}: {[s.id for s in examples_sections]}"
    )
    ids = [s.id for s in examples_sections]
    assert ids[0] != ids[1], f"Both 'Examples' sections share the same id: {ids[0]!r}"

    # Every stored key must equal the item's own .id field.
    for key, sec in index.sections.items():
        assert key == sec.id, f"Key {key!r} != section.id {sec.id!r}"


def test_skip_dirs_prunes_venv(tmp_path: pathlib.Path) -> None:
    """Files inside .venv are not indexed; files at repo root are."""
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "junk.py").write_text("def should_be_skipped(): pass\n")
    (tmp_path / "real.py").write_text("def real_fn(): pass\n")

    index = build_index(str(tmp_path), embeddings=False)

    symbol_names = {s.name for s in index.symbols.values()}
    assert "real_fn" in symbol_names, "'real_fn' from real.py was not indexed"
    assert "should_be_skipped" not in symbol_names, (
        "'should_be_skipped' from .venv/ was indexed but should have been pruned"
    )


def test_empty_repo_returns_empty_index(tmp_path: pathlib.Path) -> None:
    """build_index on an empty directory returns an Index with all empty collections."""
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir()

    index = build_index(str(empty_dir), embeddings=False)

    assert index.symbols == {}, f"Expected no symbols, got {index.symbols}"
    assert index.sections == {}, f"Expected no sections, got {index.sections}"
    assert index.links == [], f"Expected no links, got {index.links}"


def test_empty_repo_writes_loadable_file(tmp_path: pathlib.Path) -> None:
    """build_index on an empty directory still writes a loadable JSON file when asked."""
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir()
    output = tmp_path / "i.json"

    build_index(str(empty_dir), output_path=str(output), embeddings=False)

    assert output.exists(), "Output file was not written for empty repo"
    data = json.loads(output.read_text())
    assert "symbols" in data and "sections" in data and "links" in data
