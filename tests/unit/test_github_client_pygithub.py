import sys
from unittest.mock import MagicMock

import github  # PyGithub is installed; used to raise the not-found exception
from src.github.client import PyGithubClient
from src.github.summary import MARKER


def test_importing_client_module_does_not_import_pygithub():
    sys.modules.pop("github", None)
    sys.modules.pop("src.github.client", None)
    import src.github.client  # noqa: F401
    assert "github" not in sys.modules  # lazy: only imported inside methods


def test_upsert_edits_existing_marker_comment(monkeypatch):
    repo = MagicMock()
    existing = MagicMock()
    existing.body = f"{MARKER}\nold summary"
    pr = repo.get_pull.return_value
    pr.get_issue_comments.return_value = [existing]
    client = PyGithubClient("o/r", "tok")
    monkeypatch.setattr(client, "_repo", lambda: repo)

    client.upsert_summary_comment(7, "new body")

    existing.edit.assert_called_once_with("new body")
    pr.create_issue_comment.assert_not_called()


def test_upsert_creates_when_no_marker(monkeypatch):
    repo = MagicMock()
    pr = repo.get_pull.return_value
    pr.get_issue_comments.return_value = []
    client = PyGithubClient("o/r", "tok")
    monkeypatch.setattr(client, "_repo", lambda: repo)

    client.upsert_summary_comment(7, "new body")

    pr.create_issue_comment.assert_called_once_with("new body")


def test_open_fix_pr_force_updates_branch_and_creates_pr(monkeypatch):
    repo = MagicMock()
    repo.get_branch.return_value.commit.sha = "headsha"
    # branch ref does not exist yet → get_git_ref raises → create_git_ref
    repo.get_git_ref.side_effect = github.GithubException(404, "nf", None)
    # file does not exist → get_contents raises → create_file
    repo.get_contents.side_effect = github.GithubException(404, "nf", None)
    repo.get_pulls.return_value = []
    repo.create_pull.return_value.html_url = "https://github.com/o/r/pull/12"
    client = PyGithubClient("o/r", "tok")
    monkeypatch.setattr(client, "_repo", lambda: repo)

    url = client.open_or_update_fix_pr(
        "feature", "main", "docsmith/fix-pr-7", {"README.md": "new"}, "title", "body"
    )

    assert url == "https://github.com/o/r/pull/12"
    repo.create_git_ref.assert_called_once()
    repo.create_file.assert_called_once()
    repo.create_pull.assert_called_once()
