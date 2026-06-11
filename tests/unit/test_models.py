"""Unit tests for src.models core data classes."""

import pytest

from src.models import DocSection, Index, Link, Symbol


def test_symbol_fields_and_hashable():
    """Symbol exposes all fields and is hashable (can be placed in a set)."""
    sym = Symbol(
        id="app.py::create_user",
        name="create_user",
        qualified_name="app.create_user",
        kind="function",
        signature="def create_user(username: str, email: str) -> User:",
        docstring="Create a new user account.",
        file="app.py",
        start_line=42,
        end_line=58,
        language="python",
    )

    assert sym.id == "app.py::create_user"
    assert sym.name == "create_user"
    assert sym.qualified_name == "app.create_user"
    assert sym.kind == "function"
    assert sym.signature == "def create_user(username: str, email: str) -> User:"
    assert sym.docstring == "Create a new user account."
    assert sym.file == "app.py"
    assert sym.start_line == 42
    assert sym.end_line == 58
    assert sym.language == "python"

    # Hashability: frozen dataclasses must be usable as set members.
    assert {sym} == {sym}


def test_empty_index_defaults():
    """An empty Index() has empty symbols, sections, and links collections."""
    idx = Index()

    assert idx.symbols == {}
    assert idx.sections == {}
    assert idx.links == []


def test_doc_section_fields_and_hashable():
    """DocSection exposes all fields, enforces tuple types, and is hashable."""
    section = DocSection(
        id="docs/guide.md#installation",
        heading_path=("Guide", "Installation"),
        file="docs/guide.md",
        raw="## Installation\n\nRun `pip install docsmith` to get started.",
        start_line=10,
        end_line=20,
        referenced_symbols=("docsmith.install",),
        referenced_config_keys=(),
    )

    assert section.id == "docs/guide.md#installation"
    assert section.heading_path == ("Guide", "Installation")
    assert isinstance(section.heading_path, tuple)
    assert section.file == "docs/guide.md"
    assert section.start_line == 10
    assert section.end_line == 20
    assert section.referenced_symbols == ("docsmith.install",)
    assert section.referenced_config_keys == ()
    assert isinstance(section.referenced_config_keys, tuple)

    # Hashability: frozen dataclasses must be usable as set members.
    assert hash(section) == hash(section)
    assert section in {section}


def test_link_fields_and_hashable():
    """Link exposes all fields and is hashable."""
    link = Link(
        symbol_id="app.py::create_user",
        section_id="docs/guide.md#installation",
        via="symbol-match",
        score=0.85,
    )

    assert link.symbol_id == "app.py::create_user"
    assert link.section_id == "docs/guide.md#installation"
    assert link.via == "symbol-match"
    assert link.score == pytest.approx(0.85)

    # Hashability: frozen dataclasses must be usable as set members.
    assert hash(link) == hash(link)
    assert link in {link}
