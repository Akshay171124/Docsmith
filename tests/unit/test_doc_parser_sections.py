"""Tests for parse_markdown: heading-delimited section splitting."""

from pathlib import Path

from src.parsing.doc_parser import parse_markdown

FIXTURE = Path("tests/fixtures/sample_repo/README.md")


def _section_by_heading(sections, heading_path):
    """Return the first section whose heading_path matches, or None."""
    for s in sections:
        if s.heading_path == heading_path:
            return s
    return None


def test_all_heading_paths_present():
    """parse_markdown returns sections for every ATX heading in the file."""
    sections = parse_markdown(str(FIXTURE))
    paths = {s.heading_path for s in sections}
    assert ("Sample App",) in paths
    assert ("Users",) in paths
    assert ("Formatting",) in paths
    assert ("Config",) in paths


def test_users_section_properties():
    """The Users section has correct raw content, line numbers, file, and id."""
    sections = parse_markdown(str(FIXTURE))
    users = _section_by_heading(sections, ("Users",))
    assert users is not None, "Expected a section with heading_path ('Users',)"

    assert "create_user" in users.raw
    assert users.start_line < users.end_line
    assert users.file.endswith("README.md")
    assert users.id == "tests/fixtures/sample_repo/README.md#users"


def test_users_section_rel_path_id_and_file():
    """When rel_path is given, Users section id and file reflect rel_path."""
    sections = parse_markdown(str(FIXTURE), rel_path="README.md")
    users = _section_by_heading(sections, ("Users",))
    assert users is not None, "Expected a section with heading_path ('Users',)"
    assert users.id == "README.md#users"
    assert users.file == "README.md"
