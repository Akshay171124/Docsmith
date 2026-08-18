"""Analyze a public PR through the Docsmith pipeline and shape the output as JSON."""

from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass

from src.detection.investigator import investigate_pr, make_client
from src.index.builder import build_index
from src.repair.engine import repair_pr
from src.utils.config import load_settings
from webapp.prfetch import fetch_pr

# Serializes `analyze` calls: the Anthropic key is plumbed through the process-global
# environment, so two concurrent requests would otherwise cross-contaminate each
# other's credentials. Doubles as the deploy's in-process concurrency cap.
_ANALYZE_LOCK = threading.Lock()


@dataclass(frozen=True)
class SectionResult:
    """One stale documentation section and its proposed fix.

    Attributes:
        file: Doc file path.
        section_id: ``file#slug`` identifier.
        symbol_id: The code symbol whose change implicated this section.
        route: ``autofix`` / ``flag`` / ``skipped``.
        confidence: The investigator's staleness confidence (0-1).
        reason: The investigator's explanation.
        wrong_claims: Statements in the section that are no longer accurate.
        diff: Unified diff of the proposed correction (empty when none).
    """

    file: str
    section_id: str
    symbol_id: str
    route: str
    confidence: float
    reason: str
    wrong_claims: list[str]
    diff: str


@dataclass(frozen=True)
class AnalyzeResult:
    """The playground's analysis of a PR.

    Attributes:
        summary: Counts keyed by ``verified``/``auto_fixable``/``flagged``/``skipped``.
        results: One entry per stale section.
    """

    summary: dict[str, int]
    results: list[SectionResult]


def _shape(inv_result, repair_result) -> AnalyzeResult:
    """Join investigation verdicts with repair outcomes and build the API-facing result.

    Args:
        inv_result: The `InvestigationResult` from `investigate_pr` (has `.verdicts`).
        repair_result: The `RepairResult` from `repair_pr` (has `.outcomes`, `.verified`,
            `.skipped`).

    Returns:
        An `AnalyzeResult` with one `SectionResult` per stale verdict, and a `summary`
        dict of counts.
    """
    outcome_by_key = {
        (o.proposal.symbol_id, o.proposal.section_id): o for o in repair_result.outcomes
    }
    results: list[SectionResult] = []
    for verdict in inv_result.verdicts:
        if not verdict.stale:
            continue
        outcome = outcome_by_key.get((verdict.symbol_id, verdict.section_id))
        results.append(
            SectionResult(
                file=verdict.section_id.rsplit("#", 1)[0],
                section_id=verdict.section_id,
                symbol_id=verdict.symbol_id,
                route=outcome.route.value if outcome else "skipped",
                confidence=verdict.confidence,
                reason=verdict.reason,
                wrong_claims=list(verdict.wrong_claims),
                diff=outcome.proposal.diff if outcome else "",
            )
        )
    summary = {
        "verified": repair_result.verified,
        "auto_fixable": sum(1 for o in repair_result.outcomes if o.route.value == "autofix"),
        "flagged": sum(1 for o in repair_result.outcomes if o.route.value == "flag"),
        "skipped": sum(repair_result.skipped.values()),
    }
    return AnalyzeResult(summary=summary, results=results)


def analyze(
    pr_url: str,
    backend: str,
    *,
    api_key: str | None = None,
    ollama_host: str | None = None,
    model: str | None = None,
    embeddings: bool = False,
) -> AnalyzeResult:
    """Fetch a public PR, run detection -> investigation -> repair, and shape the result.

    Args:
        pr_url: A public GitHub PR URL.
        backend: LLM backend (``ollama``/``claude``/``fake``).
        api_key: Anthropic key (Claude only); set into the environment only for the
            duration of this call and never persisted or logged. Calls are serialized
            on a module-level lock so concurrent requests cannot see each other's key.
        ollama_host: Ollama base URL override.
        model: Model name override for the chosen backend.
        embeddings: Whether to build the index with embeddings (default False for speed;
            uses symbol-name-only linking).

    Returns:
        An `AnalyzeResult` with a summary of route counts and one `SectionResult` per
        stale section.

    Raises:
        ValueError: Bad URL / missing / oversized repo (propagated from `fetch_pr`).
        RuntimeError: Backend unavailable (propagated from the LLM client).
    """
    settings = load_settings()
    settings.llm_backend = backend
    if ollama_host:
        settings.ollama_host = ollama_host
    if model:
        if backend == "claude":
            settings.claude_model = model
        else:
            settings.ollama_model = model

    token = os.environ.get("GITHUB_TOKEN")
    workdir = tempfile.TemporaryDirectory()
    try:
        with _ANALYZE_LOCK:
            previous_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
            try:
                repo, base, head = fetch_pr(pr_url, workdir.name, token=token)
                index_path = os.path.join(workdir.name, "index.json")
                build_index(repo, output_path=index_path, embeddings=embeddings, full=True)
                client = make_client(settings, backend_override=backend)
                inv_result = investigate_pr(repo, base, head, index_path, settings, client)
                repair_result = repair_pr(repo, base, head, index_path, settings, client)
                return _shape(inv_result, repair_result)
            finally:
                if api_key:
                    if previous_key is None:
                        os.environ.pop("ANTHROPIC_API_KEY", None)
                    else:
                        os.environ["ANTHROPIC_API_KEY"] = previous_key
    finally:
        workdir.cleanup()
