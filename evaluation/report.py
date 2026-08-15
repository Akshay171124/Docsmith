"""Aggregate an evaluation run into a README metrics table."""

from __future__ import annotations

import json

from evaluation.models import MetricsReport

MARKER = "<!-- docsmith:results -->"


def load_run(path: str) -> MetricsReport:
    """Load the ``report`` section of a run JSON into a MetricsReport.

    Args:
        path: Path to a run JSON file (shape ``{"report": {...}, "results": [...]}``).

    Returns:
        The parsed MetricsReport.
    """
    with open(path) as fh:
        data = json.load(fh)
    return MetricsReport(**data["report"])


def render_table(report: MetricsReport) -> str:
    """Render a MetricsReport as a markdown table block (prefixed with the marker).

    Args:
        report: The metrics to render.

    Returns:
        A markdown block whose first line is ``MARKER``.
    """
    return "\n".join([
        MARKER,
        "",
        f"_Suite: **{report.suite}** · backend: **{report.backend}** "
        f"({report.model or 'n/a'}) · {report.n_cases} cases_",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision | {report.precision:.2f} |",
        f"| Recall | {report.recall:.2f} |",
        f"| F1 | {report.f1:.2f} |",
        f"| Correction exact-match | {report.exact_match_rate:.2f} |",
        f"| Correction similarity | {report.mean_similarity:.2f} |",
    ])


def update_readme(readme_path: str, table: str, marker: str = MARKER) -> None:
    """Insert or replace a marked '## Results' block in the README (idempotent).

    Args:
        readme_path: Path to the README.
        table: The rendered table (its first line is the marker).
        marker: The hidden marker identifying the managed block.
    """
    with open(readme_path) as fh:
        text = fh.read()

    body = table if marker in table else f"{marker}\n{table}"
    block = f"## Results\n\n{body}\n"
    start = text.find("## Results")
    if start != -1 and marker in text:
        end = text.find("\n## ", start + 1)
        if end == -1:
            end = len(text)
        new_text = text[:start] + block + text[end:]
    else:
        new_text = text.rstrip() + "\n\n" + block

    with open(readme_path, "w") as fh:
        fh.write(new_text)
