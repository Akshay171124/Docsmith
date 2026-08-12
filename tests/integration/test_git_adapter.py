"""Integration tests for the git adapter: real git repo -> list[FileChange]."""

from __future__ import annotations

import subprocess

from src.detection.git_adapter import collect_changes

APP_PY_V1 = """\
def greet(name):
    return "Hello, " + name
"""

APP_PY_V2 = """\
def greet(name):
    return f"Hello, {name}!"
"""

NEW_PY = """\
def farewell(name):
    return f"Goodbye, {name}!"
"""


def _run_git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo, message):
    _run_git(repo, "add", "-A")
    _run_git(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-m",
        message,
    )
    return _run_git(repo, "rev-parse", "HEAD")


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    (repo / "app.py").write_text(APP_PY_V1)
    (repo / "README.md").write_text("# Sample project\n")
    base_sha = _commit(repo, "initial commit")
    return repo, base_sha


def test_collect_changes_across_modify_add_delete(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    (repo / "app.py").write_text(APP_PY_V2)
    (repo / "new.py").write_text(NEW_PY)
    (repo / "README.md").unlink()
    (repo / "notes.txt").write_text("some unrelated notes\n")
    head_sha = _commit(repo, "modify app, add new, remove readme, add notes")

    changes = collect_changes(str(repo), base_sha, head_sha)
    by_path = {c.path: c for c in changes}

    # Modified file: both contents present, changed lines non-empty.
    app = by_path["app.py"]
    assert app.old_content is not None
    assert app.new_content is not None
    assert 'return "Hello, " + name' in app.old_content
    assert 'return f"Hello, {name}!"' in app.new_content
    assert app.changed_lines

    # Added file: no old content, new content present.
    new_file = by_path["new.py"]
    assert new_file.old_content is None
    assert new_file.new_content is not None
    assert "def farewell(name):" in new_file.new_content

    # Deleted markdown file: kept (docs are always indexed), new_content is None.
    readme = by_path["README.md"]
    assert readme.new_content is None
    assert readme.old_content is not None

    # Unsupported extension must be filtered out entirely.
    assert "notes.txt" not in by_path


def test_collect_changes_treats_rename_as_delete_plus_add(tmp_path):
    repo, base_sha = _init_repo(tmp_path)

    _run_git(repo, "mv", "app.py", "app_renamed.py")
    head_sha = _commit(repo, "rename app.py")

    changes = collect_changes(str(repo), base_sha, head_sha)
    by_path = {c.path: c for c in changes}

    # Old path is a logical delete: no content at head.
    old_entry = by_path["app.py"]
    assert old_entry.old_content is not None
    assert old_entry.new_content is None

    # New path is a logical add: no content at base.
    new_entry = by_path["app_renamed.py"]
    assert new_entry.old_content is None
    assert new_entry.new_content is not None
    assert "def greet(name):" in new_entry.new_content
