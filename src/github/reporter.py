"""Stage 9: post the summary comment and open/update the companion fix-PR. Never merges."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.detection.models import RepairResult, RepairRoute
from src.github.apply import apply_corrections
from src.github.client import GitHubClient
from src.github.context import PRContext
from src.github.summary import build_summary
from src.models import Index
from src.utils.config import Settings


@dataclass(frozen=True)
class ReportCounts:
    """Counts written to the Action's outputs.

    Attributes:
        verified: Sections confirmed still accurate.
        fixed: AUTOFIX corrections (opened in the fix-PR when auto-fix is on).
        flagged: Sections flagged for human review.
        fix_pr_url: URL of the companion fix-PR, or None if none was opened.
    """

    verified: int
    fixed: int
    flagged: int
    fix_pr_url: str | None


def report(
    result: RepairResult,
    pr_context: PRContext,
    settings: Settings,
    client: GitHubClient,
    index: Index,
    read_file: Callable[[str], str],
) -> ReportCounts:
    """Open/update the companion fix-PR (if enabled) and upsert the summary comment.

    Args:
        result: The repair result to report.
        pr_context: The pull request being reported on.
        settings: Configuration (``auto_fix`` gates opening the fix-PR).
        client: The GitHub write-side client.
        index: The current index, for AUTOFIX section spans.
        read_file: Reads a doc file's current content by repo-relative path.

    Returns:
        A ReportCounts summarising what was reported.

    Raises:
        RuntimeError: If a GitHub API call fails (propagated from the client).
    """
    autofix = [o for o in result.outcomes if o.route is RepairRoute.AUTOFIX]
    flag = [o for o in result.outcomes if o.route is RepairRoute.FLAG]

    fix_pr_url: str | None = None
    if settings.auto_fix and autofix:
        files = apply_corrections(result.outcomes, index, read_file)
        if files:
            branch = f"docsmith/fix-pr-{pr_context.pr_number}"
            title = f"docs: sync documentation for #{pr_context.pr_number}"
            body = (
                f"Automated documentation corrections for #{pr_context.pr_number}.\n\n"
                "Review and merge if correct. Docsmith never auto-merges."
            )
            fix_pr_url = client.open_or_update_fix_pr(
                pr_context.head_ref, pr_context.base_ref, branch, files, title, body
            )

    summary = build_summary(result, fix_pr_url, settings.auto_fix)
    client.upsert_summary_comment(pr_context.pr_number, summary)

    return ReportCounts(
        verified=result.verified, fixed=len(autofix), flagged=len(flag), fix_pr_url=fix_pr_url
    )
