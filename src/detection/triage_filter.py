"""Stage 4: deterministically drop noise (whitespace/comment-only, tests, pure refactors)."""

from __future__ import annotations

import fnmatch

from src.detection.models import ChangedSymbol, ChangeKind, FileChange
from src.parsing.languages import language_for_path
from src.utils.config import Settings

# Per-language single-line comment marker, used by the comment-only heuristic.
_COMMENT_MARKERS: dict[str, str] = {
    "python": "#",
    "typescript": "//",
    "javascript": "//",
    "go": "//",
}


def _matches(path: str, patterns: list[str]) -> bool:
    """Return True if ``path`` matches any of the given glob ``patterns``."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _span_changed_lines(symbol: ChangedSymbol, fc: FileChange) -> list[str]:
    """Return the text of the changed lines within ``symbol``'s span, if any."""
    if fc.new_content is None:
        return []
    span_changed = {n for n in fc.changed_lines if symbol.start_line <= n <= symbol.end_line}
    if not span_changed:
        return []
    lines = fc.new_content.splitlines()
    result = []
    for n in span_changed:
        if 1 <= n <= len(lines):
            result.append(lines[n - 1])
    return result


def triage(
    changed_symbols: list[ChangedSymbol],
    file_changes: list[FileChange],
    settings: Settings,
) -> tuple[list[ChangedSymbol], dict[str, int]]:
    """Drop changed symbols that cannot affect documentation.

    Args:
        changed_symbols: Symbols to filter, in detection order.
        file_changes: File-level diffs, used to inspect the text of changed lines.
        settings: Triage configuration (ignore globs, whitespace/comment toggles).

    Returns:
        A tuple of (kept symbols, dropped counts keyed by reason). ``dropped`` only
        contains reasons that occurred at least once.
    """
    by_path = {fc.path: fc for fc in file_changes}
    kept: list[ChangedSymbol] = []
    dropped: dict[str, int] = {}

    for symbol in changed_symbols:
        if _matches(symbol.file, settings.ignore_paths) or _matches(
            symbol.file, settings.doc_ignore
        ):
            dropped["ignored_path"] = dropped.get("ignored_path", 0) + 1
            continue

        if symbol.kind == ChangeKind.BODY_CHANGED:
            fc = by_path.get(symbol.file)
            if fc is not None:
                span_lines = _span_changed_lines(symbol, fc)

                if settings.skip_whitespace_only and span_lines:
                    if all(line.strip() == "" for line in span_lines):
                        dropped["whitespace_only"] = dropped.get("whitespace_only", 0) + 1
                        continue

                if settings.skip_comment_only and span_lines:
                    marker = _COMMENT_MARKERS.get(language_for_path(symbol.file))
                    if marker is not None and all(
                        line.strip() == "" or line.strip().startswith(marker)
                        for line in span_lines
                    ):
                        dropped["comment_only"] = dropped.get("comment_only", 0) + 1
                        continue

        kept.append(symbol)

    return kept, dropped
