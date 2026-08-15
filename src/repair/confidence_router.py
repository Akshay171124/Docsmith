"""Stage 8: route high-confidence -> fix-PR, low-confidence -> inline flag."""

from __future__ import annotations

from src.detection.models import ChangeKind, RepairProposal, RepairRoute, ValidationResult
from src.utils.config import Settings


def route(
    proposal: RepairProposal,
    validation: ValidationResult | None,
    change_kind: ChangeKind,
    verdict_confidence: float,
    settings: Settings,
) -> tuple[RepairRoute, str]:
    """Decide how to route a repair proposal, deterministically.

    A proposal is AUTOFIX only when it is a real change, the validator passed on all
    three axes, the change kind is configured as auto-fixable, and the investigator's
    staleness confidence meets the threshold. Everything else FLAGs for human review;
    a no-op rewrite is NO_CHANGE.

    Args:
        proposal: The proposed rewrite.
        validation: The validator's judgment, or None when the proposal did not change.
        change_kind: The kind of change made to the underlying symbol.
        verdict_confidence: The investigator's staleness confidence (0.0-1.0).
        settings: Repair routing configuration.

    Returns:
        A (RepairRoute, reason) tuple; ``reason`` explains the decision.
    """
    if not proposal.changed:
        return RepairRoute.NO_CHANGE, "rewrite made no change"

    clean = (
        validation is not None
        and validation.accurate
        and validation.preserved
        and validation.style_ok
    )
    mechanical = change_kind.value in settings.repair_autofix_change_kinds
    confident = verdict_confidence >= settings.repair_confidence_threshold

    if clean and mechanical and confident:
        return (
            RepairRoute.AUTOFIX,
            f"validated; {change_kind.value}; confidence {verdict_confidence:.2f}",
        )

    reasons: list[str] = []
    if not clean:
        reasons.append("validation flagged")
    if not mechanical:
        reasons.append(f"{change_kind.value} not auto-fixable")
    if not confident:
        reasons.append(
            f"confidence {verdict_confidence:.2f} < {settings.repair_confidence_threshold}"
        )
    return RepairRoute.FLAG, "; ".join(reasons)
