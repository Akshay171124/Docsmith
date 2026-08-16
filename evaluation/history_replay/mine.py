"""Mine a repo's coupled code+doc commits into replay cases (real-world ground truth)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from evaluation.models import Case, Gold
from src.parsing.code_parser import parse_source
from src.parsing.doc_parser import parse_markdown
from src.parsing.languages import language_for_path


def _git(repo: str, *args: str) -> str:
    """Run a git command in the given repo and return its stdout.

    Args:
        repo: Path to the git repo.
        args: Git subcommand and arguments.

    Returns:
        The command's stdout.
    """
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    ).stdout


def _show(repo: str, ref: str, path: str) -> str | None:
    """Fetch a file's content at a given ref via `git show`.

    Args:
        repo: Path to the git repo.
        ref: Commit-ish to read the file at.
        path: Repo-relative file path.

    Returns:
        The file's content at that ref, or None if the file doesn't exist there.
    """
    try:
        return subprocess.run(
            ["git", "-C", repo, "show", f"{ref}:{path}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None


def _parse_markdown_content(content: str, rel_path: str):
    """Parse in-memory markdown content into DocSections.

    `parse_markdown` reads from a filesystem path, so the content is written to a
    temporary file first; `rel_path` is passed through so DocSection.id/.file use the
    real repo-relative path (e.g. "README.md#users") rather than the temp path.

    Args:
        content: Markdown file content.
        rel_path: Repo-relative path used for DocSection.id and DocSection.file.

    Returns:
        A list of DocSection objects.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / "doc.md"
        tmp_file.write_text(content, encoding="utf-8")
        return parse_markdown(str(tmp_file), rel_path=rel_path)


def _changed_symbol_names(repo: str, parent: str, commit: str, path: str) -> set[str]:
    """Bare names of symbols whose source text differs between parent and commit.

    Args:
        repo: Path to the git repo.
        parent: Parent commit-ish.
        commit: Commit-ish.
        path: Repo-relative code file path.

    Returns:
        Bare symbol names that were added, removed, or whose text changed.
    """
    language = language_for_path(path)
    if language is None:
        return set()
    old = _show(repo, parent, path)
    new = _show(repo, commit, path)

    def _by_name(content: str | None) -> dict[str, str]:
        if content is None:
            return {}
        out: dict[str, str] = {}
        lines = content.splitlines()
        for sym in parse_source(content, path, language):
            out[sym.name] = "\n".join(lines[sym.start_line - 1 : sym.end_line])
        return out

    old_syms, new_syms = _by_name(old), _by_name(new)
    changed = set()
    for name in set(old_syms) | set(new_syms):
        if old_syms.get(name) != new_syms.get(name):
            changed.add(name)
    return changed


def mine_cases(
    repo_path: str, base: str, head: str, *, max_cases: int | None = None
) -> list[Case]:
    """Mine coupled code+doc commits in ``base..head`` into replay cases.

    Walks commits oldest-first. A commit qualifies when it touches at least one
    supported-language code file and one markdown doc file, at least one changed
    code symbol's source text differs between the commit and its parent, and at
    least one section of a changed doc file (parsed at the commit) references one
    of those changed symbol names. For qualifying commits, the doc edit is hidden
    at head (head_files keeps the pre-edit doc) while the code edit is applied at
    head, and the gold labels record the coupled section ids and their post-edit
    text as the expected fix.

    Args:
        repo_path: Path to the git repo to mine.
        base: Older ref (exclusive).
        head: Newer ref (inclusive).
        max_cases: Optional cap on the number of cases returned.

    Returns:
        One Case per commit whose doc edit references a symbol changed in the same commit.
    """
    revs = _git(repo_path, "rev-list", "--reverse", f"{base}..{head}").split()
    cases: list[Case] = []
    for commit in revs:
        parents = _git(repo_path, "rev-list", "--parents", "-n", "1", commit).split()
        if len(parents) < 2:
            continue
        parent = parents[1]
        changed = _git(repo_path, "diff", "--name-only", parent, commit).split()
        code_files = [f for f in changed if language_for_path(f) is not None]
        doc_files = [f for f in changed if f.endswith(".md")]
        if not code_files or not doc_files:
            continue

        changed_names: set[str] = set()
        for f in code_files:
            changed_names |= _changed_symbol_names(repo_path, parent, commit, f)
        if not changed_names:
            continue

        stale_ids: set[str] = set()
        fixes: dict[str, str] = {}
        base_files: dict[str, str] = {}
        head_files: dict[str, str] = {}
        skip_commit = False
        for f in doc_files:
            content_c = _show(repo_path, commit, f)
            content_p = _show(repo_path, parent, f)
            if content_c is None or content_p is None:
                skip_commit = True
                break
            for section in _parse_markdown_content(content_c, f):
                if set(section.referenced_symbols) & changed_names:
                    stale_ids.add(section.id)
                    fixes[section.id] = section.raw
            base_files[f] = content_p
            head_files[f] = content_p  # doc hidden: head keeps the pre-edit doc
        if skip_commit or not stale_ids:
            continue

        for f in code_files:
            p_content = _show(repo_path, parent, f)
            c_content = _show(repo_path, commit, f)
            if p_content is not None:
                base_files[f] = p_content
            if c_content is not None:
                head_files[f] = c_content

        cases.append(
            Case(
                case_id=f"history-{commit[:10]}",
                base_files=base_files,
                head_files=head_files,
                gold=Gold(stale_section_ids=frozenset(stale_ids), fixes=fixes),
            )
        )
        if max_cases is not None and len(cases) >= max_cases:
            break
    return cases
