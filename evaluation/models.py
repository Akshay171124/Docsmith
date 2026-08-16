"""Data models for the evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Gold:
    """Ground-truth labels for one replay case.

    Attributes:
        stale_section_ids: Section ids that SHOULD be flagged stale (empty = a negative case).
        fixes: Section id → expected corrected text (may be empty for detection-only cases).
    """

    stale_section_ids: frozenset[str]
    fixes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Case:
    """A self-contained replay case as file-pairs plus gold labels.

    Attributes:
        case_id: Unique identifier.
        base_files: repo-relative path → content for the base revision.
        head_files: repo-relative path → content for the head revision.
        gold: Ground-truth labels.
    """

    case_id: str
    base_files: dict[str, str]
    head_files: dict[str, str]
    gold: Gold


@dataclass(frozen=True)
class CaseResult:
    """Scored outcome for one case.

    Attributes:
        case_id: The case's id.
        tp: Correctly-flagged sections. fp: Wrongly-flagged. fn: Missed stale sections.
        corrections: Per-correction scores ``{"exact": bool, "similarity": float}``.
    """

    case_id: str
    tp: int
    fp: int
    fn: int
    corrections: tuple[dict, ...] = ()


@dataclass(frozen=True)
class MetricsReport:
    """Aggregated metrics for a suite run.

    Attributes:
        suite/backend/model: Run identity. n_cases: cases scored.
        tp/fp/fn: summed detection counts. precision/recall/f1: derived.
        n_corrections: corrections scored. exact_match_rate/mean_similarity: correction quality.
    """

    suite: str
    backend: str
    model: str
    n_cases: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    n_corrections: int
    exact_match_rate: float
    mean_similarity: float
