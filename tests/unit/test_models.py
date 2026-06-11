"""Unit tests for src.models core data classes."""

from src.models import Index, Symbol


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
