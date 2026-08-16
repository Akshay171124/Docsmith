"""Integration tests for history-replay mining of coupled code+doc commits."""

import subprocess

from evaluation.history_replay.mine import mine_cases


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)


def _setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "e@x.com")
    _git(repo, "config", "user.name", "E")
    (repo / "app.py").write_text("def create_user(name):\n    return name\n")
    (repo / "README.md").write_text("# D\n\n## Users\n\nCall `create_user`.\n")
    _commit(repo, "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # coupled commit: change create_user signature AND its doc section together
    (repo / "app.py").write_text("def create_user(name, email):\n    return name\n")
    (repo / "README.md").write_text(
        "# D\n\n## Users\n\nCall `create_user` with name and email.\n"
    )
    _commit(repo, "coupled")
    # uncoupled commit: unrelated code + a doc typo fix that names no changed symbol
    (repo / "util.py").write_text("def helper():\n    return 2\n")
    (repo / "README.md").write_text(
        "# Docs\n\n## Users\n\nCall `create_user` with name and email.\n"
    )
    _commit(repo, "uncoupled")
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repo, base, head


def test_mine_keeps_only_coupled_commit(tmp_path):
    repo, base, head = _setup(tmp_path)
    cases = mine_cases(str(repo), base, head)
    assert len(cases) == 1
    case = cases[0]
    assert case.gold.stale_section_ids == frozenset({"README.md#users"})
    # doc hidden at head (equals base doc); code updated at head
    assert case.base_files["README.md"] == case.head_files["README.md"]
    assert "email" in case.head_files["app.py"]
    assert "with name and email" in case.gold.fixes["README.md#users"]
