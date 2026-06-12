"""Build the index (full scan) and update it incrementally for changed files."""

from __future__ import annotations

import dataclasses
import os

from src.index.embeddings import BgeSmallEmbedder, Embedder, VectorStore
from src.index.hashing import classify_changes, hash_file
from src.index.linker import link_by_embedding, link_by_name, merge_links
from src.index.store import load_index, save_index
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


def _symbol_text(sym: Symbol) -> str:
    """Build a searchable text representation of a symbol for embedding.

    Args:
        sym: The Symbol to represent.

    Returns:
        A multi-line string combining kind, qualified name, signature, and docstring.
    """
    text = f"{sym.kind} {sym.qualified_name}\n{sym.signature}"
    if sym.docstring:
        text += f"\n{sym.docstring}"
    return text


def _section_text(sec: DocSection) -> str:
    """Build a searchable text representation of a doc section for embedding.

    Args:
        sec: The DocSection to represent.

    Returns:
        A multi-line string combining the heading path and raw body text.
    """
    return f"{' > '.join(sec.heading_path)}\n{sec.raw}"


def build_index(
    repo_root: str,
    output_path: str | None = None,
    *,
    embeddings: bool = True,
    full: bool = False,
    embedder: Embedder | None = None,
    top_k: int = 5,
    threshold: float = 0.55,
) -> Index:
    """Walk repo_root and build a hybrid code-docs index.

    Parses all supported source files for symbols and all Markdown files for
    doc sections, records file hashes, then links them by name and optionally
    by embedding similarity, assembling a complete Index.

    Args:
        repo_root: Root directory of the repository to index.
        output_path: If provided, the index is persisted to this path as JSON.
        embeddings: When True, also embed symbols and sections into a vector
            store and run embedding-based linking in addition to name matching.
            When False, only name-based linking is performed and no VectorStore
            is constructed.
        full: Retained for CLI compatibility; no longer gates the store reset.
            The vector store is always reset by build_index (see comment below).
        embedder: Embedder instance to use when embeddings is True.  Defaults
            to BgeSmallEmbedder() when None.  Intended as a test injection seam.
        top_k: Maximum number of symbol candidates to retrieve per section
            during embedding-based linking.
        threshold: Minimum cosine similarity for an embedding hit to be emitted
            as a Link.

    Returns:
        The assembled Index containing symbols, sections, links, and file_hashes.
    """
    symbols: dict[str, Symbol] = {}
    sections: dict[str, DocSection] = {}
    file_hashes: dict[str, str] = {}

    for file_path in _walk(repo_root):
        rel = os.path.relpath(file_path, repo_root)
        if language_for_path(file_path) is not None:
            for sym in parse_file(file_path, rel_path=rel):
                _add_unique(symbols, sym)
            file_hashes[rel] = hash_file(file_path)
        elif file_path.lower().endswith(".md"):
            for sec in parse_markdown(file_path, rel_path=rel):
                _add_unique(sections, sec)
            file_hashes[rel] = hash_file(file_path)

    index = Index(symbols=symbols, sections=sections, links=[], file_hashes=file_hashes)

    if embeddings:
        emb = embedder or BgeSmallEmbedder()

        if output_path is not None:
            persist_dir = os.path.join(os.path.dirname(output_path) or ".", "chroma")
        else:
            persist_dir = os.path.join(repo_root, ".docsmith", "chroma")

        store = VectorStore(emb, persist_dir)
        # build_index is always a clean rebuild — never upsert onto stale vectors.
        store.reset()

        store.add("symbol", [(s.id, _symbol_text(s), s.file) for s in symbols.values()])
        # NOTE: section vectors are stored for a future stored-vector recall path;
        # link_by_embedding currently re-embeds section text at query time.
        store.add("section", [(c.id, _section_text(c), c.file) for c in sections.values()])

        symbol_links = link_by_name(symbols, sections)
        embedding_links = link_by_embedding(sections, store, _section_text, top_k, threshold)
        index.links = merge_links(symbol_links, embedding_links)
    else:
        index.links = link_by_name(symbols, sections)

    if output_path is not None:
        save_index(index, output_path)

    return index


def _build_current_hashes(repo_root: str) -> dict[str, str]:
    """Return a ``{rel_path: sha256}`` map for all indexable files under repo_root.

    Mirrors the file-selection logic of ``build_index``: includes files whose
    path maps to a supported language and Markdown files; skips everything else.

    Args:
        repo_root: Root directory of the repository.

    Returns:
        Dict mapping repo-relative paths to their SHA-256 hex digests.
    """
    file_hashes: dict[str, str] = {}
    for file_path in _walk(repo_root):
        rel = os.path.relpath(file_path, repo_root)
        if language_for_path(file_path) is not None or file_path.lower().endswith(".md"):
            file_hashes[rel] = hash_file(file_path)
    return file_hashes


def _parse_files(
    repo_root: str,
    rel_paths: set[str],
) -> tuple[list[Symbol], list[DocSection]]:
    """Parse a set of repo-relative paths and return their symbols and sections.

    Args:
        repo_root: Root directory of the repository.
        rel_paths: Set of repo-relative paths to parse.

    Returns:
        A tuple ``(symbols, sections)`` with all parsed entities from those files.
    """
    symbols: list[Symbol] = []
    sections: list[DocSection] = []
    for rel in rel_paths:
        abs_path = os.path.join(repo_root, rel)
        if language_for_path(abs_path) is not None:
            symbols.extend(parse_file(abs_path, rel_path=rel))
        elif abs_path.lower().endswith(".md"):
            sections.extend(parse_markdown(abs_path, rel_path=rel))
    return symbols, sections


def update_index(
    repo_root: str,
    output_path: str,
    *,
    embeddings: bool = True,
    embedder: Embedder | None = None,
    top_k: int = 5,
    threshold: float = 0.55,
) -> Index:
    """Incrementally update a persisted index for files that changed since last build.

    Loads the existing index from *output_path*, detects which files were added,
    changed, or deleted by comparing file hashes, removes stale entries, re-parses
    only the affected files, and fully recomputes all links.

    Args:
        repo_root: Root directory of the repository to index.
        output_path: Path of the persisted index JSON (must already exist).
        embeddings: When True, also maintain the vector store: delete stale
            vectors and embed only the newly parsed entities. When False, only
            name-based linking is performed.
        embedder: Embedder instance to use when embeddings is True. Defaults to
            ``BgeSmallEmbedder()`` when None. Intended as a test injection seam.
        top_k: Maximum number of symbol candidates to retrieve per section during
            embedding-based linking.
        threshold: Minimum cosine similarity for an embedding hit to be emitted
            as a Link.

    Returns:
        The updated Index, also persisted back to *output_path*.
    """
    index = load_index(output_path)

    current_hashes = _build_current_hashes(repo_root)
    changes = classify_changes(current_hashes, index.file_hashes)

    stale = changes.changed | changes.deleted

    # Remove stale symbols and sections
    index.symbols = {sid: sym for sid, sym in index.symbols.items() if sym.file not in stale}
    index.sections = {
        sec_id: sec for sec_id, sec in index.sections.items() if sec.file not in stale
    }

    persist_dir = os.path.join(os.path.dirname(output_path) or ".", "chroma")

    store: VectorStore | None = None
    if embeddings:
        emb = embedder or BgeSmallEmbedder()
        store = VectorStore(emb, persist_dir)
        store.delete_by_files(stale)

    # Parse added and changed files, insert new entities
    to_reparse = changes.added | changes.changed
    new_symbols, new_sections = _parse_files(repo_root, to_reparse)

    for sym in new_symbols:
        _add_unique(index.symbols, sym)
    for sec in new_sections:
        _add_unique(index.sections, sec)

    if embeddings and store is not None:
        # Collect only the entities from the re-parsed files for embedding
        reparsed_files = to_reparse
        new_sym_items = [
            (s.id, _symbol_text(s), s.file)
            for s in index.symbols.values()
            if s.file in reparsed_files
        ]
        new_sec_items = [
            (c.id, _section_text(c), c.file)
            for c in index.sections.values()
            if c.file in reparsed_files
        ]
        store.add("symbol", new_sym_items)
        store.add("section", new_sec_items)

    index.file_hashes = current_hashes

    # Fully recompute links
    symbol_links = link_by_name(index.symbols, index.sections)
    if embeddings and store is not None:
        index.links = merge_links(
            symbol_links, link_by_embedding(index.sections, store, _section_text, top_k, threshold)
        )
    else:
        index.links = symbol_links

    save_index(index, output_path)

    added_count = len(changes.added)
    changed_count = len(changes.changed)
    deleted_count = len(changes.deleted)
    print(f"update: +{added_count} ~{changed_count} -{deleted_count} files")

    return index
