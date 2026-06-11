"""Unit tests for src.index.linker.link_by_name.

Tests cover exact bare-name matching, no-match behaviour, and method symbols
where the bare name differs from the qualified name.
"""

from __future__ import annotations

import pytest

from src.models import DocSection, Symbol

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def make_symbol(
    name: str,
    *,
    qualified_name: str | None = None,
    kind: str = "function",
    sym_id: str | None = None,
    file: str = "src/app.py",
    language: str = "python",
) -> Symbol:
    """Return a minimal Symbol with only the fields under test varied."""
    qn = qualified_name if qualified_name is not None else name
    sid = sym_id if sym_id is not None else f"{file}::{qn}"
    return Symbol(
        id=sid,
        name=name,
        qualified_name=qn,
        kind=kind,
        signature=f"def {name}():",
        docstring=None,
        file=file,
        start_line=1,
        end_line=5,
        language=language,
    )


def make_section(
    referenced_symbols: tuple[str, ...],
    *,
    section_id: str = "docs/guide.md#usage",
    file: str = "docs/guide.md",
) -> DocSection:
    """Return a minimal DocSection with the given referenced_symbols."""
    return DocSection(
        id=section_id,
        heading_path=("Usage",),
        file=file,
        raw="",
        start_line=1,
        end_line=10,
        referenced_symbols=referenced_symbols,
        referenced_config_keys=(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_exact_name_match_produces_one_link():
    """A section referencing 'create_user' and one symbol named 'create_user' → one Link."""
    from src.index.linker import link_by_name

    sym = make_symbol("create_user")
    section = make_section(("create_user",))

    links = link_by_name({sym.id: sym}, {section.id: section})

    assert len(links) == 1
    link = links[0]
    assert link.symbol_id == sym.id
    assert link.section_id == section.id
    assert link.via == "symbol-match"
    assert link.score == pytest.approx(1.0)


def test_no_match_returns_empty_list():
    """A section referencing an unknown name with no matching symbol → empty list."""
    from src.index.linker import link_by_name

    sym = make_symbol("create_user")
    section = make_section(("unknown_function",))

    links = link_by_name({sym.id: sym}, {section.id: section})

    assert links == []


def test_method_bare_name_links_via_referenced_bare_name():
    """A method with name='deactivate', qualified_name='UserService.deactivate'
    links when a section references the bare name 'deactivate'.
    """
    from src.index.linker import link_by_name

    method = make_symbol(
        "deactivate",
        qualified_name="UserService.deactivate",
        kind="method",
        sym_id="src/services.py::UserService.deactivate",
    )
    section = make_section(("deactivate",))

    links = link_by_name({method.id: method}, {section.id: section})

    assert len(links) == 1
    assert links[0].symbol_id == method.id
    assert links[0].via == "symbol-match"
    assert links[0].score == pytest.approx(1.0)
