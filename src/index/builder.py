"""Build the index (full scan) and update it incrementally for changed files."""

from __future__ import annotations

import dataclasses
import os

from src.index.linker import link_by_name
from src.index.store import save_index
from src.models import DocSection, Index, Symbol
from src.parsing.code_parser import parse_file
from src.parsing.doc_parser import parse_markdown
from src.parsing.languages import language_for_path

_SKIP_DIRS = {".git", ".docsmith", "node_modules", ".venv", "venv", "__pycache__"}


def _add_unique(mapping: dict, item) -> None:
    """Insert item into mapping keyed by item.id, disambiguating on collision.

    On an id collision, appends '#2', '#3', ... until unique, and updates the
    stored item's `id` so it always equals its dict key.

    Args:
        mapping: The dict to insert into (mutated in place).
        item: A frozen dataclass with an `id` field.
    """
    key = item.id
    if key in mapping:
        n = 2
        while f"{key}#{n}" in mapping:
            n += 1
        key = f"{key}#{n}"
        item = dataclasses.replace(item, id=key)
    mapping[key] = item


def _walk(repo_root: str):
    """Yield every file path under repo_root, skipping noise directories.

    Args:
        repo_root: Root directory to walk.

    Yields:
        Absolute or relative file paths (preserving repo_root prefix).
    """
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            yield os.path.join(dirpath, filename)


def build_index(repo_root: str, output_path: str | None = None) -> Index:
    """Walk repo_root and build a full code-docs index.

    Parses all supported source files for symbols and all Markdown files for
    doc sections, then links them by name and assembles an Index.

    Args:
        repo_root: Root directory of the repository to index.
        output_path: If provided, the index is persisted to this path as JSON.

    Returns:
        The assembled Index containing symbols, sections, and links.
    """
    symbols: dict[str, Symbol] = {}
    sections: dict[str, DocSection] = {}

    for file_path in _walk(repo_root):
        if language_for_path(file_path) is not None:
            for sym in parse_file(file_path):
                _add_unique(symbols, sym)
        elif file_path.lower().endswith(".md"):
            for sec in parse_markdown(file_path):
                _add_unique(sections, sec)

    links = link_by_name(symbols, sections)
    index = Index(symbols=symbols, sections=sections, links=links)

    if output_path is not None:
        save_index(index, output_path)

    return index
