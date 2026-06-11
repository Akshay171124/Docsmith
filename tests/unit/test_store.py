"""Tests for src.index.store: JSON round-trip for the Index dataclass."""

from __future__ import annotations

import os

import pytest

from src.index.store import load_index, save_index
from src.models import DocSection, Index, Link, Symbol

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SYMBOL = Symbol(
    id="src/foo.py::Foo.bar",
    name="bar",
    qualified_name="Foo.bar",
    kind="method",
    signature="def bar(self) -> None",
    docstring="Does bar things.",
    file="src/foo.py",
    start_line=10,
    end_line=15,
    language="python",
)

SECTION = DocSection(
    id="docs/guide.md#usage",
    heading_path=("Guide", "Usage"),
    file="docs/guide.md",
    raw="Call `Foo.bar()` to do bar things.",
    start_line=5,
    end_line=12,
    referenced_symbols=("Foo.bar",),
    referenced_config_keys=(),
)

LINK = Link(
    symbol_id="src/foo.py::Foo.bar",
    section_id="docs/guide.md#usage",
    via="symbol-match",
    score=0.95,
)


def _make_index() -> Index:
    return Index(
        symbols={SYMBOL.id: SYMBOL},
        sections={SECTION.id: SECTION},
        links=[LINK],
    )


# ---------------------------------------------------------------------------
# Test 1: full round-trip correctness
# ---------------------------------------------------------------------------


def test_round_trip(tmp_path):
    """save_index then load_index reproduces all fields exactly."""
    path = str(tmp_path / "index.json")
    original = _make_index()

    save_index(original, path)
    loaded = load_index(path)

    # Symbol field survives
    loaded_symbol = loaded.symbols[SYMBOL.id]
    assert loaded_symbol.name == SYMBOL.name

    # Section heading_path survives and remains a tuple
    loaded_section = loaded.sections[SECTION.id]
    assert loaded_section.heading_path == SECTION.heading_path
    assert isinstance(loaded_section.heading_path, tuple), (
        "heading_path must be a tuple, not a list"
    )

    # Section referenced_symbols survives and remains a tuple
    assert loaded_section.referenced_symbols == SECTION.referenced_symbols
    assert isinstance(loaded_section.referenced_symbols, tuple), (
        "referenced_symbols must be a tuple, not a list"
    )

    # Section referenced_config_keys survives and remains a tuple
    assert loaded_section.referenced_config_keys == SECTION.referenced_config_keys
    assert isinstance(loaded_section.referenced_config_keys, tuple), (
        "referenced_config_keys must be a tuple, not a list"
    )

    # Link fields survive
    loaded_link = loaded.links[0]
    assert loaded_link.via == LINK.via
    assert loaded_link.score == pytest.approx(LINK.score)

    # Full equality checks (also proves hashability/frozen invariant holds)
    assert loaded_symbol == SYMBOL
    assert loaded_section == SECTION
    assert loaded_link == LINK


# ---------------------------------------------------------------------------
# Test 2: nested parent directories are created automatically
# ---------------------------------------------------------------------------


def test_save_creates_parent_directories(tmp_path):
    """save_index creates missing intermediate directories."""
    nested_path = str(tmp_path / ".docsmith" / "index.json")
    save_index(_make_index(), nested_path)

    assert os.path.isfile(nested_path), "index.json was not created at the nested path"
