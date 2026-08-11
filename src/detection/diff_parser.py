"""Stage 1: parse the PR diff into changed files and hunks."""

from __future__ import annotations

from unidiff import PatchSet


def parse_unified_diff(diff_text: str) -> dict[str, frozenset[int]]:
    """Parse a unified diff into added new-file line numbers per file.

    Each patched file is keyed by its **target (new) path** for additions and
    modifications, since those are the line numbers callers care about. A file
    that is purely a deletion (no added lines, including fully deleted files)
    is instead keyed by its **source (old) path** — the target path is
    `/dev/null` and can't identify the file — and maps to an empty frozenset.

    Files with no hunks (e.g. binary or mode-only changes) are skipped
    entirely.

    Args:
        diff_text: Raw unified diff text (e.g. from `git diff`).

    Returns:
        Mapping of file path to the frozenset of new-file line numbers that
        were added in that file.
    """
    patch_set = PatchSet(diff_text)
    result: dict[str, frozenset[int]] = {}

    for patched_file in patch_set:
        if len(patched_file) == 0:
            continue

        added_lines = {
            line.target_line_no
            for hunk in patched_file
            for line in hunk
            if line.is_added
        }

        key = patched_file.source_file.removeprefix("a/") if not added_lines else patched_file.path
        result[key] = frozenset(added_lines)

    return result
