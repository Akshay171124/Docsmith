"""Load pull-request context from the GitHub Actions environment + event payload."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PRContext:
    """Identifying details of the pull request the Action is running on.

    Attributes:
        repo: Repository in ``"owner/name"`` form.
        base_sha: SHA of the PR's base (target) commit.
        head_sha: SHA of the PR's head (source) commit.
        pr_number: The pull request number.
        head_ref: The PR's head branch name.
        base_ref: The PR's base branch name.
    """

    repo: str
    base_sha: str
    head_sha: str
    pr_number: int
    head_ref: str
    base_ref: str


def load_pr_context(env: Mapping[str, str]) -> PRContext:
    """Build a PRContext from the Actions env vars and the event payload file.

    Args:
        env: Environment mapping (typically ``os.environ``) with ``GITHUB_REPOSITORY``
            and ``GITHUB_EVENT_PATH`` set.

    Returns:
        A populated PRContext.

    Raises:
        ValueError: If required env vars are missing or the event is not a
            ``pull_request`` payload.
    """
    repo = env.get("GITHUB_REPOSITORY")
    event_path = env.get("GITHUB_EVENT_PATH")
    if not repo or not event_path:
        raise ValueError("GITHUB_REPOSITORY and GITHUB_EVENT_PATH must be set")

    with open(event_path) as fh:
        event = json.load(fh)

    pr = event.get("pull_request")
    if pr is None:
        raise ValueError("not a pull_request event: 'pull_request' missing from event payload")

    return PRContext(
        repo=repo,
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        pr_number=event.get("number", pr.get("number")),
        head_ref=pr["head"]["ref"],
        base_ref=pr["base"]["ref"],
    )
