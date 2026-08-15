"""Materialize a Case into a scratch two-commit git repo the pipeline can replay."""

from __future__ import annotations

import os
import shutil
import subprocess

from evaluation.models import Case


def _git(repo: str, *args: str) -> None:
    """Run a git command in ``repo``, raising on non-zero exit."""
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _rev(repo: str) -> str:
    """Return the current HEAD sha of ``repo``."""
    return subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _write_tree(repo: str, files: dict[str, str]) -> None:
    """Replace the repo's non-.git contents with ``files``."""
    for entry in os.listdir(repo):
        if entry == ".git":
            continue
        path = os.path.join(repo, entry)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    real_repo = os.path.realpath(repo)
    for rel, content in files.items():
        dest = os.path.realpath(os.path.join(repo, rel))
        if dest != real_repo and not dest.startswith(real_repo + os.sep):
            raise ValueError(f"unsafe path in case files: {rel!r}")
        os.makedirs(os.path.dirname(dest) or real_repo, exist_ok=True)
        with open(dest, "w") as fh:
            fh.write(content)


def materialize_case(case: Case, workdir: str) -> tuple[str, str, str]:
    """Build a two-commit git repo (base -> head) for a case.

    Args:
        case: The case to materialize.
        workdir: A directory to create the repo under.

    Returns:
        ``(repo_path, base_sha, head_sha)``.
    """
    repo = os.path.join(workdir, "repo")
    os.makedirs(repo, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "eval@example.com")
    _git(repo, "config", "user.name", "Docsmith Eval")

    _write_tree(repo, case.base_files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _rev(repo)

    _write_tree(repo, case.head_files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "head")
    head = _rev(repo)

    return repo, base, head
