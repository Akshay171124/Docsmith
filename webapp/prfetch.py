"""Fetch a public GitHub pull request into a scratch git repo for analysis."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

_PR_URL_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)/?$")

MAX_REPO_KB = 200_000  # ~200 MB reported repo size cap for the playground


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse a public GitHub PR URL into ``(owner, repo, number)``.

    Args:
        url: A ``https://github.com/{owner}/{repo}/pull/{n}`` URL.

    Returns:
        The ``(owner, repo, number)`` triple.

    Raises:
        ValueError: If ``url`` is not a public GitHub pull-request URL.
    """
    match = _PR_URL_RE.match(url.strip())
    if match is None:
        raise ValueError(f"not a public GitHub pull-request URL: {url!r}")
    owner, repo, number = match.group(1), match.group(2), int(match.group(3))
    return owner, repo, number


def fetch_pr(
    pr_url: str, workdir: str, *, token: str | None = None
) -> tuple[str, str, str]:
    """Clone a public PR's base repo into ``workdir`` and fetch its head commit.

    Args:
        pr_url: A public GitHub pull-request URL.
        workdir: A directory to create the clone under.
        token: Optional GitHub token — only raises the API rate limit.

    Returns:
        ``(repo_path, base_sha, head_sha)``; both commits are present in the clone.

    Raises:
        ValueError: If the URL is invalid, the PR/repo is missing (404), or the repo
            exceeds the size cap.
    """
    owner, repo, number = parse_pr_url(pr_url)
    api = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    request = urllib.request.Request(
        api,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "docsmith-playground",
        },
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(
                "PR or repository not found (must be a public GitHub PR)"
            ) from exc
        raise

    size_kb = data["base"]["repo"].get("size", 0)
    if size_kb > MAX_REPO_KB:
        raise ValueError(f"repository too large for the playground ({size_kb} KB)")

    base_sha = data["base"]["sha"]
    head_sha = data["head"]["sha"]
    clone_url = data["base"]["repo"]["clone_url"]

    repo_path = os.path.join(workdir, "repo")
    _git("clone", clone_url, repo_path)
    # The PR head is reachable via GitHub's pull/<n>/head ref on the base repo
    # (fork-safe).
    _git("-C", repo_path, "fetch", "origin", f"pull/{number}/head")
    return repo_path, base_sha, head_sha
