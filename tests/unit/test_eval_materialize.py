import subprocess

from evaluation.materialize import materialize_case
from evaluation.models import Case, Gold


def _show(repo, ref, path):
    return subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{path}"], check=True, capture_output=True, text=True
    ).stdout


def test_materialize_creates_two_commits(tmp_path):
    case = Case(
        case_id="c1",
        base_files={"app.py": "def f():\n    return 1\n", "README.md": "# D\n\nUse `f`.\n"},
        head_files={"app.py": "def f(x):\n    return x\n", "README.md": "# D\n\nUse `f`.\n"},
        gold=Gold(stale_section_ids=frozenset()),
    )
    repo, base, head = materialize_case(case, str(tmp_path))
    assert base != head
    assert _show(repo, base, "app.py") == "def f():\n    return 1\n"
    assert _show(repo, head, "app.py") == "def f(x):\n    return x\n"
    # README identical across both commits (docs unchanged in this case)
    assert _show(repo, base, "README.md") == _show(repo, head, "README.md")


def test_materialize_handles_file_removal(tmp_path):
    case = Case(
        case_id="c2",
        base_files={"a.py": "x\n", "b.py": "y\n"},
        head_files={"a.py": "x2\n"},  # b.py removed at head
        gold=Gold(stale_section_ids=frozenset()),
    )
    repo, base, head = materialize_case(case, str(tmp_path))
    files_at_head = subprocess.run(
        ["git", "-C", repo, "ls-tree", "--name-only", head],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert "a.py" in files_at_head and "b.py" not in files_at_head
