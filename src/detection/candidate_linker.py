"""Stage 3: link changed symbols to suspect doc sections (symbol-match + embedding recall)."""

from __future__ import annotations

from src.detection.models import ChangedSymbol, Suspect
from src.models import Index


def find_suspects(changed_symbols: list[ChangedSymbol], index: Index) -> list[Suspect]:
    """Map changed symbols to candidate stale doc sections.

    Two independent recall paths are combined for each changed symbol, in this
    priority order:

    - ``index-link``: sections already linked to the symbol's id in
      ``index.links`` (built by the Week-1/2 symbol-match + embedding linker).
    - ``name-reference``: doc sections whose ``referenced_symbols`` mention the
      symbol's unqualified name, even when no persisted link exists. This is
      the only path that catches ``REMOVED`` symbols, since a removed symbol
      has no entry left in the head index to link against.

    When a ``(symbol_id, section_id)`` pair is reachable via both paths, only
    the ``index-link`` suspect is kept.

    Output order is deterministic: all index-link suspects first (in
    changed_symbols order, then in the order their links appear in
    ``index.links``), followed by the remaining name-reference-only suspects
    (in changed_symbols order, then sorted by section_id).

    Args:
        changed_symbols: Symbols found to have changed by the diff/symbol-mapper
            stages, in the order they should be processed.
        index: The current code/docs index to search for related doc sections.

    Returns:
        A deduplicated, deterministically ordered list of Suspect candidates.
    """
    suspects: list[Suspect] = []
    seen: set[tuple[str, str]] = set()

    for cs in changed_symbols:
        for link in index.links:
            if link.symbol_id != cs.id:
                continue
            pair = (cs.id, link.section_id)
            if pair in seen:
                continue
            seen.add(pair)
            suspects.append(
                Suspect(
                    symbol_id=cs.id,
                    section_id=link.section_id,
                    change_kind=cs.kind,
                    via="index-link",
                )
            )

    for cs in changed_symbols:
        matching_section_ids = sorted(
            section.id
            for section in index.sections.values()
            if cs.name in section.referenced_symbols
        )
        for section_id in matching_section_ids:
            pair = (cs.id, section_id)
            if pair in seen:
                continue
            seen.add(pair)
            suspects.append(
                Suspect(
                    symbol_id=cs.id,
                    section_id=section_id,
                    change_kind=cs.kind,
                    via="name-reference",
                )
            )

    return suspects
