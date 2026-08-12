"""Stage 0: turn a git ref range into the FileChanges the detection pipeline consumes."""

from __future__ import annotations

import subprocess

from src.detection.diff_parser import parse_unified_diff
from src.detection.models import FileChange
from src.parsing.languages import language_for_path


def _is_indexed_path(path: str) -> bool:
    """Return whether Docsmith indexes this path (a supported code language or Markdown)."""
    return language_for_path(path) is not None or path.lower().endswith(".md")


def _run_git(repo_root: str, *args: str) -> str:
    """Run a git subcommand in repo_root and return its decoded stdout."""
    result = subprocess.run(
        ["git", "-C", repo_root, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _parse_name_status(output: str) -> list[tuple[str, str, str | None]]:
    """Parse `git diff --name-status` output into (status, path, old_path) entries.

    Args:
        output: Raw stdout of `git diff --name-status <base> <head>`.

    Returns:
        A list of tuples. For ordinary statuses (A/M/D), `old_path` is None and
        `path` is the single reported path. For renames/copies (R###/C###),
        `old_path` is the source path and `path` is the destination path.
    """
    entries: list[tuple[str, str, str | None]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        status = fields[0]
        if status.startswith("R") or status.startswith("C"):
            old_path, new_path = fields[1], fields[2]
            entries.append((status[0], new_path, old_path))
        else:
            entries.append((status[0], fields[1], None))
    return entries


def collect_changes(repo_root: str, base: str, head: str) -> list[FileChange]:
    """Collect FileChanges for every Docsmith-indexed file that differs between two refs.

    Renames are treated as a logical delete of the old path plus a logical add of the
    new path, since symbol-level diffing operates per-path and has no notion of a file
    being "the same file" across a rename.

    Args:
        repo_root: Path to the git working tree.
        base: Base ref (old revision).
        head: Head ref (new revision).

    Returns:
        A FileChange for each changed, indexed file. Content for a side of the change
        that is known (from the status) not to exist is left as None rather than
        fetched from git.
    """
    name_status_output = _run_git(repo_root, "diff", "--name-status", base, head)
    diff_output = _run_git(repo_root, "diff", "--unified", base, head)
    changed_lines_by_path = parse_unified_diff(diff_output)

    # Each logical change is (path, existed_at_base, existed_at_head).
    logical_changes: list[tuple[str, bool, bool]] = []
    for status, path, old_path in _parse_name_status(name_status_output):
        if status == "A":
            logical_changes.append((path, False, True))
        elif status == "D":
            logical_changes.append((path, True, False))
        elif status == "M":
            logical_changes.append((path, True, True))
        elif status in ("R", "C") and old_path is not None:
            if status == "R":
                logical_changes.append((old_path, True, False))
            logical_changes.append((path, False, True))
        # Other statuses (e.g. type changes) are ignored.

    changes: list[FileChange] = []
    for path, existed_at_base, existed_at_head in logical_changes:
        if not _is_indexed_path(path):
            continue

        old_content = _run_git(repo_root, "show", f"{base}:{path}") if existed_at_base else None
        new_content = _run_git(repo_root, "show", f"{head}:{path}") if existed_at_head else None
        changed_lines = changed_lines_by_path.get(path, frozenset())

        changes.append(
            FileChange(
                path=path,
                old_content=old_content,
                new_content=new_content,
                changed_lines=changed_lines,
            )
        )

    return changes
