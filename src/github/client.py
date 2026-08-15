"""GitHub write-side seam: summary comment + companion fix-PR.

The protocol has a scripted ``FakeGitHubClient`` for offline tests and a real
``PyGithubClient`` that lazy-imports PyGithub (so importing this module needs no
SDK, token, or network). ``PyGithubClient`` is added in a later task.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GitHubClient(Protocol):
    """Write-side operations Docsmith performs on a pull request."""

    def upsert_summary_comment(self, pr_number: int, body: str) -> None:
        """Create or update Docsmith's summary comment on a PR.

        Args:
            pr_number: The pull request number to comment on.
            body: The full markdown body to set for the comment.
        """
        ...

    def open_or_update_fix_pr(
        self,
        head_ref: str,
        base_ref: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str:
        """Create or update a companion fix pull request.

        Args:
            head_ref: The ref the fix branch is created from.
            base_ref: The base branch the fix PR targets.
            branch: The name of the branch to create or update.
            files: Mapping of file path to new file contents to commit.
            title: The pull request title.
            body: The pull request body.

        Returns:
            The URL of the created or updated pull request.
        """
        ...


class FakeGitHubClient:
    """Offline, scripted GitHubClient for tests: records calls, returns a canned URL."""

    def __init__(self, fix_pr_url: str = "https://github.com/fake/repo/pull/999") -> None:
        self._fix_pr_url = fix_pr_url
        self.comments: dict[int, str] = {}
        self.comment_calls = 0
        self.fix_prs: list[dict] = []

    def upsert_summary_comment(self, pr_number: int, body: str) -> None:
        """Record the comment body for ``pr_number``, overwriting any prior value."""
        self.comments[pr_number] = body
        self.comment_calls += 1

    def open_or_update_fix_pr(
        self,
        head_ref: str,
        base_ref: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str:
        """Record the fix-PR call and return the constructor-provided URL."""
        self.fix_prs.append(
            {
                "head_ref": head_ref,
                "base_ref": base_ref,
                "branch": branch,
                "files": files,
                "title": title,
                "body": body,
            }
        )
        return self._fix_pr_url
