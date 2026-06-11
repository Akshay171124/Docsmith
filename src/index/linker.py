"""Deterministic symbol-to-section linker.

Links doc sections to code symbols by exact bare-name match, using only the
``referenced_symbols`` field already extracted during parsing.  No embeddings
or LLM calls are made here — those are handled in a later stage.
"""

from __future__ import annotations

from collections import defaultdict

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
