"""GitHub write-side seam: summary comment + companion fix-PR.

The protocol has a scripted ``FakeGitHubClient`` for offline tests and a real
``PyGithubClient`` that lazy-imports PyGithub (so importing this module needs no
SDK, token, or network).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.github.summary import MARKER


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


class PyGithubClient:
    """Real GitHubClient backed by PyGithub. Lazy-imports ``github`` inside methods."""

    def __init__(self, repo: str, token: str) -> None:
        self._repo_name = repo
        self._token = token
        self._repo_handle = None

    def _repo(self):  # noqa: ANN202 - PyGithub Repository type is not imported at module scope
        """Return a cached PyGithub Repository handle, importing the SDK lazily."""
        if self._repo_handle is None:
            import github

            self._repo_handle = github.Github(self._token).get_repo(self._repo_name)
        return self._repo_handle

    def upsert_summary_comment(self, pr_number: int, body: str) -> None:
        """Edit Docsmith's existing summary comment if present, else create it."""
        pr = self._repo().get_pull(pr_number)
        for comment in pr.get_issue_comments():
            if MARKER in comment.body:
                comment.edit(body)
                return
        pr.create_issue_comment(body)

    def open_or_update_fix_pr(
        self,
        head_ref: str,
        base_ref: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str:
        """Force-update the fix branch off head, commit files, open/update the PR."""
        import github

        repo = self._repo()
        head_sha = repo.get_branch(head_ref).commit.sha

        try:
            ref = repo.get_git_ref(f"heads/{branch}")
            ref.edit(head_sha, force=True)
        except github.GithubException:
            repo.create_git_ref(f"refs/heads/{branch}", head_sha)

        for path, content in files.items():
            try:
                existing = repo.get_contents(path, ref=branch)
                repo.update_file(path, f"docs: update {path}", content, existing.sha, branch=branch)
            except github.GithubException:
                repo.create_file(path, f"docs: create {path}", content, branch=branch)

        owner = self._repo_name.split("/")[0]
        pulls = list(repo.get_pulls(state="open", head=f"{owner}:{branch}", base=base_ref))
        if pulls:
            pulls[0].edit(title=title, body=body)
            return pulls[0].html_url
        return repo.create_pull(title=title, body=body, base=base_ref, head=branch).html_url
