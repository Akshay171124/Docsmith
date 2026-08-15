"""Apply AUTOFIX corrections into doc-file content (deterministic span-replace)."""

from __future__ import annotations

from collections.abc import Callable

from src.detection.models import RepairOutcome, RepairRoute
from src.models import Index


def apply_corrections(
    outcomes: list[RepairOutcome],
    index: Index,
    read_file: Callable[[str], str],
) -> dict[str, str]:
    """Produce corrected file content for each doc file touched by an AUTOFIX outcome.

    Args:
        outcomes: All repair outcomes; only AUTOFIX ones are applied.
        index: The current index, for each section's line span.
        read_file: Reads a doc file's current content by repo-relative path.

    Returns:
        A mapping of doc-file path to its new full content. Files with no applicable
        AUTOFIX edit are absent. Multiple edits to one file are applied bottom-up so
        earlier edits do not shift later line numbers; the file's trailing newline is
        preserved.
    """
    by_file: dict[str, list] = {}
    for outcome in outcomes:
        if outcome.route is not RepairRoute.AUTOFIX:
            continue
        section = index.sections.get(outcome.proposal.section_id)
        if section is None:
            continue
        by_file.setdefault(section.file, []).append((section, outcome.proposal))

    result: dict[str, str] = {}
    for file, edits in by_file.items():
        original = read_file(file)
        lines = original.splitlines()
        for section, proposal in sorted(edits, key=lambda e: e[0].start_line, reverse=True):
            lines[section.start_line - 1 : section.end_line] = proposal.revised_text.splitlines()
        trailing = "\n" if original.endswith("\n") else ""
        result[file] = "\n".join(lines) + trailing

    return result
