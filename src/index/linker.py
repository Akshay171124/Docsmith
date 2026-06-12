"""Deterministic symbol-to-section linker.

Links doc sections to code symbols by exact bare-name match, using only the
``referenced_symbols`` field already extracted during parsing.  Embedding-based
recall and hybrid merging are also provided here for the later retrieval stage.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from src.index.embeddings import VectorStore
from src.models import DocSection, Link, Symbol


def link_by_name(
    symbols: dict[str, Symbol],
    sections: dict[str, DocSection],
) -> list[Link]:
    """Produce Links between symbols and sections by matching bare symbol names.

    For every name listed in a section's ``referenced_symbols``, emit one Link
    per symbol whose bare ``name`` equals that referenced name.  Symbols whose
    ``qualified_name`` differs from their ``name`` (e.g. methods) still match
    on the bare name.

    Args:
        symbols: Mapping of symbol id → Symbol, as stored in the index.
        sections: Mapping of section id → DocSection, as stored in the index.

    Returns:
        A list of Links, one per (symbol, section) pair that matched.  The list
        is deterministic: order follows iteration order of ``sections`` then
        ``referenced_symbols`` then the symbols that share a name.
    """
    # Build bare-name → [Symbol, ...] lookup once.
    by_name: dict[str, list[Symbol]] = defaultdict(list)
    for sym in symbols.values():
        by_name[sym.name].append(sym)

    links: list[Link] = []
    for section in sections.values():
        for ref_name in section.referenced_symbols:
            for sym in by_name.get(ref_name, []):
                links.append(
                    Link(
                        symbol_id=sym.id,
                        section_id=section.id,
                        via="symbol-match",
                        score=1.0,
                    )
                )

    return links


def link_by_embedding(
    sections: dict[str, DocSection],
    store: VectorStore,
    section_text: Callable[[DocSection], str],
    top_k: int,
    threshold: float,
) -> list[Link]:
    """Produce Links between symbols and sections via embedding similarity.

    For every section, queries the vector store for the ``top_k`` most similar
    symbols and emits a Link for each hit whose similarity meets or exceeds
    *threshold*.  Hits below the threshold are silently dropped.

    Args:
        sections: Mapping of section id → DocSection to link.
        store: Pre-populated vector store containing symbol embeddings under
            the group ``"symbol"``.
        section_text: Callable that extracts the query text from a section
            (e.g. ``lambda s: s.raw``).
        top_k: Maximum number of symbol candidates to retrieve per section.
        threshold: Minimum cosine similarity (inclusive) for a hit to be
            emitted as a Link.

    Returns:
        A list of Links with ``via="embedding"`` and ``score`` equal to the
        cosine similarity returned by the store.  Order follows iteration order
        of *sections*; within each section, hits are ordered by similarity
        descending (as returned by the store).
    """
    links: list[Link] = []
    for section in sections.values():
        query = section_text(section)
        hits = store.query(query, "symbol", top_k)
        for symbol_id, similarity in hits:
            if similarity >= threshold:
                # Clamp to [0.0, 1.0]: float32 round-trip through Chroma can
                # produce values fractionally above 1.0 for near-identical vectors.
                links.append(
                    Link(
                        symbol_id=symbol_id,
                        section_id=section.id,
                        via="embedding",
                        score=min(1.0, similarity),
                    )
                )
    return links


def merge_links(symbol_links: list[Link], embedding_links: list[Link]) -> list[Link]:
    """Merge symbol-match and embedding links into a deduplicated union.

    Pairs present in both inputs are collapsed to a single ``via="both"`` Link
    at ``score=1.0``.  Pairs found only in one input are kept as-is.  The
    output is ordered: symbol-match/both pairs first (in their original input
    order), followed by embedding-only pairs (in their original input order).
    No duplicate ``(symbol_id, section_id)`` pairs appear in the output.

    Args:
        symbol_links: Links produced by exact name matching (``via="symbol-match"``).
        embedding_links: Links produced by embedding recall (``via="embedding"``).

    Returns:
        Deduplicated list of Links with deterministic ordering.
    """
    # Build a set of (symbol_id, section_id) keys present in embedding_links.
    embedding_keys: set[tuple[str, str]] = {
        (link.symbol_id, link.section_id) for link in embedding_links
    }

    # Build a set of keys present in symbol_links to identify embedding-only pairs.
    symbol_keys: set[tuple[str, str]] = {
        (link.symbol_id, link.section_id) for link in symbol_links
    }

    result: list[Link] = []

    # First pass: emit symbol-match entries, upgrading overlapping pairs to "both".
    for link in symbol_links:
        key = (link.symbol_id, link.section_id)
        if key in embedding_keys:
            result.append(
                Link(symbol_id=link.symbol_id, section_id=link.section_id, via="both", score=1.0)
            )
        else:
            result.append(link)

    # Second pass: emit embedding-only entries (skip pairs already handled above).
    for link in embedding_links:
        key = (link.symbol_id, link.section_id)
        if key not in symbol_keys:
            result.append(link)

    return result
