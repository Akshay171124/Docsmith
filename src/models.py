"""Core data models for the Docsmith index.

These frozen dataclasses form the contract between all pipeline stages:
parsers, linker, store, and builder all construct or consume exactly these types.
Field names and order are fixed — do not rename, reorder, add, or omit fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Symbol:
    """A code symbol extracted by the parser.

    The ``id`` is formatted as ``"path::Qualified.name"``.
    ``kind`` is one of ``function``, ``class``, or ``method``.
    """

    id: str
    name: str
    qualified_name: str
    kind: str
    signature: str
    docstring: str | None
    file: str
    start_line: int
    end_line: int
    language: str


@dataclass(frozen=True)
class DocSection:
    """A section of a documentation file.

    The ``id`` is formatted as ``"file#heading-slug"``.
    ``heading_path`` is the ordered tuple of ancestor headings down to this section.
    ``referenced_symbols`` and ``referenced_config_keys`` capture cross-references
    found in the section body.
    """

    id: str
    heading_path: tuple[str, ...]
    file: str
    raw: str
    start_line: int
    end_line: int
    referenced_symbols: tuple[str, ...]
    referenced_config_keys: tuple[str, ...]


@dataclass(frozen=True)
class Link:
    """A directional link between a Symbol and a DocSection.

    ``via`` is one of ``symbol-match``, ``embedding``, or ``both``.
    ``score`` reflects the linker's confidence (higher is more confident).
    """

    symbol_id: str
    section_id: str
    via: str
    score: float


@dataclass
class Index:
    """The in-memory index mapping symbols and doc sections with their links.

    All four collections default to empty so ``Index()`` is always safe to construct.
    ``file_hashes`` maps repo-relative file paths to their hex sha256 digests and
    is used by the builder to detect changed files on incremental updates.
    """

    symbols: dict[str, Symbol] = field(default_factory=dict)
    sections: dict[str, DocSection] = field(default_factory=dict)
    links: list[Link] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
