"""Replay evaluation cases through the pipeline and score them."""

from __future__ import annotations

import logging
import os
import tempfile

from evaluation.materialize import materialize_case
from evaluation.models import Case, CaseResult, MetricsReport
from evaluation.scoring import aggregate_report, score_correction, score_detection
from src.detection.investigator import investigate_pr
from src.index.builder import build_index
from src.index.embeddings import FakeEmbedder
from src.llm.client import LLMClient
from src.repair.engine import repair_pr
from src.utils.config import Settings

logger = logging.getLogger(__name__)

_FIXTURE_ERRORS = (ValueError, KeyError, TypeError, OSError)


def _predict(case: Case, client: LLMClient, repair: bool, embeddings: bool) -> tuple[set, dict]:
    """Run the pipeline for one case; return (flagged_section_ids, proposed_fixes).

    Args:
        case: The case to replay.
        client: The LLM client used for investigation/repair.
        repair: Whether to run the repair stage (needed for correction quality).
        embeddings: Whether to build the case's index with embeddings.

    Returns:
        A tuple of the flagged section ids and a section id -> revised text map
        of the fixes the repair stage proposed for changed sections.
    """
    with tempfile.TemporaryDirectory() as workdir:
        repo, base, head = materialize_case(case, workdir)
        index_path = os.path.join(workdir, "index.json")
        build_index(repo, output_path=index_path, embeddings=embeddings, full=True)
        settings = Settings()
        if repair:
            result = repair_pr(repo, base, head, index_path, settings, client)
            flagged = {o.proposal.section_id for o in result.outcomes}
            fixes = {
                o.proposal.section_id: o.proposal.revised_text
                for o in result.outcomes
                if o.proposal.changed
            }
        else:
            inv = investigate_pr(repo, base, head, index_path, settings, client)
            flagged = {v.section_id for v in inv.verdicts if v.stale}
            fixes = {}
    return flagged, fixes


def evaluate_cases(
    cases: list[Case],
    client: LLMClient,
    *,
    embedder=None,
    repair: bool = True,
    embeddings: bool = True,
) -> list[CaseResult]:
    """Score each case by replaying it through the pipeline.

    Args:
        cases: Cases to evaluate.
        client: The LLM client (fake in tests, Ollama/Claude in live runs).
        embedder: Embedder for correction similarity (defaults to a deterministic fake).
        repair: Whether to run the repair stage (needed for correction quality).
        embeddings: Whether to build each case's index with embeddings (False offline).

    Returns:
        One CaseResult per case.

    Raises:
        RuntimeError: If the LLM backend is unavailable (propagated).
    """
    emb = embedder or FakeEmbedder()
    results: list[CaseResult] = []
    for case in cases:
        try:
            flagged, fixes = _predict(case, client, repair, embeddings)
        except RuntimeError:
            raise
        except _FIXTURE_ERRORS as exc:
            logger.warning("Case %s failed to replay: %s", case.case_id, exc)
            flagged, fixes = set(), {}

        gold_sections = set(case.gold.stale_section_ids)
        tp, fp, fn = score_detection(flagged, gold_sections)

        corrections: list[dict] = []
        for section_id in sorted(flagged & gold_sections & set(case.gold.fixes)):
            if section_id in fixes:
                corrections.append(
                    score_correction(fixes[section_id], case.gold.fixes[section_id], emb)
                )
        results.append(CaseResult(case.case_id, tp, fp, fn, tuple(corrections)))
    return results


def run_suite(
    cases: list[Case],
    client: LLMClient,
    *,
    embedder=None,
    repair: bool = True,
    embeddings: bool = True,
    suite: str,
    backend: str,
    model: str,
) -> tuple[list[CaseResult], MetricsReport]:
    """Evaluate a suite of cases and aggregate into a MetricsReport.

    Args:
        cases: Cases to evaluate.
        client: The LLM client (fake in tests, Ollama/Claude in live runs).
        embedder: Embedder for correction similarity (defaults to a deterministic fake).
        repair: Whether to run the repair stage (needed for correction quality).
        embeddings: Whether to build each case's index with embeddings (False offline).
        suite: Suite name recorded on the report.
        backend: Backend name recorded on the report.
        model: Model name recorded on the report.

    Returns:
        A tuple of the per-case results and the aggregated MetricsReport.
    """
    results = evaluate_cases(
        cases, client, embedder=embedder, repair=repair, embeddings=embeddings
    )
    report = aggregate_report(results, suite=suite, backend=backend, model=model)
    return results, report
