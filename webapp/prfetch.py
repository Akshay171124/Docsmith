"""Fetch a public GitHub pull request into a scratch git repo for analysis."""

from __future__ import annotations

import re

_PR_URL_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)/?$")


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
