"""Scoring for the evaluation harness: detection metrics + correction quality."""

from __future__ import annotations

from evaluation.models import CaseResult, MetricsReport


def score_detection(predicted: set[str], gold: set[str]) -> tuple[int, int, int]:
    """Return ``(tp, fp, fn)`` for one case's flagged sections vs. the gold set."""
    tp = len(predicted & gold)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    return tp, fp, fn


def _normalize(text: str) -> str:
    return " ".join(text.split())


def score_correction(predicted_text: str, gold_text: str, embedder) -> dict:
    """Score a proposed correction vs. gold.

    Args:
        predicted_text: The repair engine's rewritten section text.
        gold_text: The expected corrected text.
        embedder: An ``Embedder`` (real bge-small in live runs, fake in tests).

    Returns:
        ``{"exact": bool, "similarity": float}`` — normalized-string equality and embedding
        cosine similarity (dot product of unit vectors).
    """
    normalized_predicted = _normalize(predicted_text)
    normalized_gold = _normalize(gold_text)
    exact = normalized_predicted == normalized_gold
    vecs = embedder.embed_texts([normalized_predicted, normalized_gold])
    similarity = sum(a * b for a, b in zip(vecs[0], vecs[1], strict=True))
    return {"exact": exact, "similarity": similarity}


def aggregate_report(
    results: list[CaseResult], *, suite: str, backend: str, model: str
) -> MetricsReport:
    """Aggregate per-case results into a MetricsReport (precision/recall/F1 + correction stats)."""
    tp = sum(r.tp for r in results)
    fp = sum(r.fp for r in results)
    fn = sum(r.fn for r in results)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    corrections = [c for r in results for c in r.corrections]
    n_corr = len(corrections)
    exact_rate = sum(1 for c in corrections if c["exact"]) / n_corr if n_corr else 0.0
    mean_sim = sum(c["similarity"] for c in corrections) / n_corr if n_corr else 0.0

    return MetricsReport(
        suite=suite, backend=backend, model=model, n_cases=len(results),
        tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1,
        n_corrections=n_corr, exact_match_rate=exact_rate, mean_similarity=mean_sim,
    )
