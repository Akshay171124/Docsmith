"""Tests for reference extraction in doc_parser._extract_references (Task 6)."""

from __future__ import annotations

from pathlib import Path

from src.parsing.doc_parser import parse_markdown

_README = str(Path(__file__).parents[2] / "tests" / "fixtures" / "sample_repo" / "README.md")


def _sections_by_heading(path: str) -> dict[tuple[str, ...], object]:
    """Return a mapping of heading_path -> DocSection for the parsed file."""
    return {s.heading_path: s for s in parse_markdown(path)}


def test_users_section_referenced_symbols() -> None:
    """The Users section must surface create_user, UserService, and deactivate as symbols."""
    sections = _sections_by_heading(_README)
    section = sections[("Users",)]
    assert "create_user" in section.referenced_symbols
    assert "UserService" in section.referenced_symbols
    assert "deactivate" in section.referenced_symbols


def test_config_section_referenced_config_keys() -> None:
    """The Config section must surface MAX_USERS as a config key, not a symbol."""
    sections = _sections_by_heading(_README)
    section = sections[("Config",)]
    assert "MAX_USERS" in section.referenced_config_keys
    assert "MAX_USERS" not in section.referenced_symbols
