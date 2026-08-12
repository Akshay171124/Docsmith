"""Tests for src/detection/candidate_linker.py."""

from __future__ import annotations

from src.detection.candidate_linker import find_suspects
from src.detection.models import ChangedSymbol, ChangeKind
from src.index.builder import build_index
from src.models import DocSection, Index, Link, Symbol


def _symbol(id="app.py::create_user", name="create_user"):
    return Symbol(
        id=id,
        name=name,
        qualified_name=name,
        kind="function",
        signature=f"def {name}():",
        docstring=None,
        file="app.py",
        start_line=1,
        end_line=2,
        language="python",
    )


def _section(id="README.md#usage", referenced_symbols=()):
    return DocSection(
        id=id,
        heading_path=("Usage",),
        file="README.md",
        raw="some text",
        start_line=1,
        end_line=3,
        referenced_symbols=referenced_symbols,
        referenced_config_keys=(),
    )


def _changed_symbol(
    id="app.py::create_user", name="create_user", kind=ChangeKind.SIGNATURE_CHANGED
):
    return ChangedSymbol(
        id=id,
        name=name,
        qualified_name=name,
        file="app.py",
        kind=kind,
        start_line=1,
        end_line=2,
        old_signature="def create_user(name):",
        new_signature="def create_user(name, email):",
    )


def test_index_link_suspect():
    index = Index(
        symbols={"app.py::create_user": _symbol()},
        sections={"README.md#usage": _section()},
        links=[
            Link(
                symbol_id="app.py::create_user",
                section_id="README.md#usage",
                via="symbol-match",
                score=1.0,
            )
        ],
        file_hashes={},
    )
    cs = _changed_symbol(kind=ChangeKind.SIGNATURE_CHANGED)

    suspects = find_suspects([cs], index)

    assert len(suspects) == 1
    suspect = suspects[0]
    assert suspect.symbol_id == "app.py::create_user"
    assert suspect.section_id == "README.md#usage"
    assert suspect.via == "index-link"
    assert suspect.change_kind == ChangeKind.SIGNATURE_CHANGED


def test_name_reference_for_removed_symbol():
    index = Index(
        symbols={},
        sections={
            "README.md#helpers": _section(
                id="README.md#helpers", referenced_symbols=("old_helper",)
            )
        },
        links=[],
        file_hashes={},
    )
    cs = _changed_symbol(id="app.py::old_helper", name="old_helper", kind=ChangeKind.REMOVED)

    suspects = find_suspects([cs], index)

    assert len(suspects) == 1
    assert suspects[0].section_id == "README.md#helpers"
    assert suspects[0].via == "name-reference"
    assert suspects[0].change_kind == ChangeKind.REMOVED


def test_dedup_prefers_index_link():
    index = Index(
        symbols={"app.py::create_user": _symbol()},
        sections={
            "README.md#usage": _section(
                id="README.md#usage", referenced_symbols=("create_user",)
            )
        },
        links=[
            Link(
                symbol_id="app.py::create_user",
                section_id="README.md#usage",
                via="symbol-match",
                score=1.0,
            )
        ],
        file_hashes={},
    )
    cs = _changed_symbol()

    suspects = find_suspects([cs], index)

    assert len(suspects) == 1
    assert suspects[0].via == "index-link"


def test_no_match_yields_empty_list():
    index = Index(
        symbols={"app.py::create_user": _symbol()},
        sections={"README.md#usage": _section()},
        links=[],
        file_hashes={},
    )
    cs = _changed_symbol(id="app.py::unrelated", name="unrelated")

    suspects = find_suspects([cs], index)

    assert suspects == []


def test_path_alignment_against_real_index(tmp_path):
    (tmp_path / "app.py").write_text(
        "def create_user(name):\n    return {'name': name}\n"
    )
    (tmp_path / "README.md").write_text(
        "# Usage\n\nCall `create_user` to make a new user.\n"
    )

    index = build_index(str(tmp_path), output_path=None, embeddings=False)

    symbol = next(s for s in index.symbols.values() if s.name == "create_user")
    cs = _changed_symbol(id=symbol.id, name="create_user", kind=ChangeKind.SIGNATURE_CHANGED)

    assert any(link.symbol_id == cs.id for link in index.links), (
        "expected build_index to produce a Link keyed by the symbol's real id; "
        "if this fails, the ChangedSymbol id form and index Symbol id form have drifted"
    )

    suspects = find_suspects([cs], index)

    assert len(suspects) >= 1
    assert any(s.via == "index-link" for s in suspects)
