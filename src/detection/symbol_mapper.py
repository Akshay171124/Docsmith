"""Stage 2: map changed line spans to before/after code symbols (tree-sitter)."""

from __future__ import annotations

from src.detection.models import ChangedSymbol, ChangeKind, FileChange
from src.parsing.code_parser import parse_source
from src.parsing.languages import language_for_path


def map_changes(file_changes: list[FileChange]) -> list[ChangedSymbol]:
    """Classify code symbol changes from a set of file diffs.

    For each file, parses the old and new content into symbol tables keyed by
    qualified name and classifies each qualified name as added, removed,
    signature-changed, or body-changed. Unchanged symbols are omitted. Files
    whose language isn't recognized (e.g. doc files) are skipped, since
    doc-level changes are handled elsewhere.

    Args:
        file_changes: Per-file diffs to map to code symbol changes.

    Returns:
        A flat list of ChangedSymbol instances across all files.
    """
    changed_symbols: list[ChangedSymbol] = []

    for fc in file_changes:
        language = language_for_path(fc.path)
        if language is None:
            continue

        old = (
            {s.qualified_name: s for s in parse_source(fc.old_content, fc.path, language)}
            if fc.old_content
            else {}
        )
        new = (
            {s.qualified_name: s for s in parse_source(fc.new_content, fc.path, language)}
            if fc.new_content
            else {}
        )

        for qualified_name in old.keys() | new.keys():
            old_sym = old.get(qualified_name)
            new_sym = new.get(qualified_name)

            if old_sym is None:
                kind = ChangeKind.ADDED
            elif new_sym is None:
                kind = ChangeKind.REMOVED
            elif old_sym.signature != new_sym.signature:
                kind = ChangeKind.SIGNATURE_CHANGED
            elif _overlaps(new_sym.start_line, new_sym.end_line, fc.changed_lines):
                kind = ChangeKind.BODY_CHANGED
            else:
                continue

            active_sym = new_sym if new_sym is not None else old_sym
            changed_symbols.append(
                ChangedSymbol(
                    id=f"{fc.path}::{qualified_name}",
                    name=active_sym.name,
                    qualified_name=qualified_name,
                    file=fc.path,
                    kind=kind,
                    start_line=active_sym.start_line,
                    end_line=active_sym.end_line,
                    old_signature=old_sym.signature if old_sym is not None else None,
                    new_signature=new_sym.signature if new_sym is not None else None,
                )
            )

    return changed_symbols


def _overlaps(start: int, end: int, changed_lines: frozenset[int]) -> bool:
    """Check whether a symbol's line span overlaps a set of changed lines.

    Args:
        start: Start line of the symbol's span (inclusive).
        end: End line of the symbol's span (inclusive).
        changed_lines: New-file line numbers touched by the diff.

    Returns:
        True if any line in [start, end] is in changed_lines.
    """
    return any(line in changed_lines for line in range(start, end + 1))
