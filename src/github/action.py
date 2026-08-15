"""GitHub Action entrypoint core: env → settings → index → repair → report."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from src.detection.investigator import make_client
from src.github.action_settings import settings_from_env
from src.github.client import PyGithubClient
from src.github.context import load_pr_context
from src.github.reporter import ReportCounts, report
from src.index.builder import build_index
from src.index.store import load_index
from src.repair.engine import repair_pr


def run_action(
    env: Mapping[str, str],
    repo_root: str,
    *,
    embeddings: bool = True,
    llm_client=None,
    gh_client=None,
) -> ReportCounts:
    """Run the full Action pipeline for one pull request.

    Args:
        env: Environment mapping (``os.environ`` in production).
        repo_root: Path to the checked-out repository.
        embeddings: Whether to build the index with embeddings (True in production;
            tests pass False to stay offline).
        llm_client: Optional LLM client override (tests inject a FakeLLMClient).
        gh_client: Optional GitHub client override (tests inject a FakeGitHubClient).

    Returns:
        A ReportCounts for the run.

    Raises:
        RuntimeError: If the LLM backend is unavailable or a GitHub API call fails.
    """
    settings = settings_from_env(env)
    pr = load_pr_context(env)

    index_path = os.path.join(repo_root, ".docsmith", "index.json")
    build_index(repo_root, output_path=index_path, embeddings=embeddings, full=True)
    index = load_index(index_path)

    llm = llm_client or make_client(settings)
    result = repair_pr(repo_root, pr.base_sha, pr.head_sha, index_path, settings, llm)

    if gh_client is None:
        token = env.get("INPUT_GITHUB-TOKEN") or env.get("GITHUB_TOKEN") or ""
        gh_client = PyGithubClient(pr.repo, token)

    def read_file(path: str) -> str:
        return (Path(repo_root) / path).read_text()

    return report(result, pr, settings, gh_client, index, read_file)
