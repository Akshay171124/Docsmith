"""Build the Docsmith pull-request summary comment (markdown)."""

from __future__ import annotations

from src.detection.models import RepairResult, RepairRoute

MARKER = "<!-- docsmith:summary -->"


def build_summary(result: RepairResult, fix_pr_url: str | None, auto_fix: bool) -> str:
    """Render the summary comment body.

    Args:
        result: The repair result being reported.
        fix_pr_url: URL of the companion fix-PR, or None when none was opened.
        auto_fix: Whether auto-fix is enabled (controls the AUTOFIX section heading).

    Returns:
        A markdown string beginning with the hidden idempotency marker.
    """
    autofix = [o for o in result.outcomes if o.route is RepairRoute.AUTOFIX]
    flag = [o for o in result.outcomes if o.route is RepairRoute.FLAG]

    fixed_txt = f"{len(autofix)} auto-fixed"
    if fix_pr_url:
        fixed_txt += f" ([fix PR]({fix_pr_url}))"

    lines: list[str] = [
        MARKER,
        "",
        f"**Docsmith:** {result.verified} verified · {fixed_txt} · {len(flag)} flagged",
        "",
    ]

    if autofix:
        opened = auto_fix and fix_pr_url is not None
        lines.append("### Auto-fixed" if opened else "### Proposed fixes (auto-fix disabled)")
        for outcome in autofix:
            lines.append(f"- `{outcome.proposal.section_id}` — {outcome.reason}")
        lines.append("")

    if flag:
        lines.append("### Needs review")
        for outcome in flag:
            lines.append(f"- `{outcome.proposal.section_id}` — {outcome.reason}")
            lines.append("")
            lines.append("<details><summary>Proposed correction</summary>")
            lines.append("")
            lines.append("```diff")
            lines.append(outcome.proposal.diff)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    skipped = sum(result.skipped.values())
    if skipped:
        lines.append(f"_{skipped} section(s) skipped due to malformed model output._")

    lines.append("")
    lines.append("_Docsmith never auto-merges — review and merge if correct._")
    return "\n".join(lines)
