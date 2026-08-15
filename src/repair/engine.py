"""Repair orchestration: assemble inputs and run repair->validate->route per section."""

from __future__ import annotations

import logging

from src.detection.detector import run_detection
from src.detection.investigator import build_investigation_inputs, investigate
from src.detection.models import (
    FileChange,
    RepairInput,
    RepairOutcome,
    RepairResult,
    Suspect,
    Verdict,
)
from src.detection.source import extract_symbol_source
from src.index.store import load_index
from src.llm.client import LLMClient
from src.models import Index
from src.repair.confidence_router import route
from src.repair.repairer import repair_section
from src.repair.validator import validate_repair
from src.utils.config import Settings

logger = logging.getLogger(__name__)


def build_repair_inputs(
    verdicts: list[Verdict],
    suspects: list[Suspect],
    file_changes: list[FileChange],
    index: Index,
) -> list[RepairInput]:
    """Assemble per-verdict repair inputs from investigation + detection output.

    Joins each verdict to its suspect on ``(symbol_id, section_id)`` to recover the
    change kind, resolves the doc-section text from the index, and extracts the
    symbol's new source from the owning file change.

    Args:
        verdicts: Stale verdicts to repair (callers pass only ``stale`` verdicts).
        suspects: Detection suspects, used to recover each verdict's change kind.
        file_changes: The diffs the suspects were derived from.
        index: The current index, used to resolve doc section text.

    Returns:
        One RepairInput per unique ``(symbol_id, section_id)`` verdict whose suspect
        and section are both present. Verdicts without a matching suspect or section
        are skipped.
    """
    change_kind_by_key = {(s.symbol_id, s.section_id): s.change_kind for s in suspects}
    by_path = {fc.path: fc for fc in file_changes}
    seen: set[tuple[str, str]] = set()
    inputs: list[RepairInput] = []

    for verdict in verdicts:
        key = (verdict.symbol_id, verdict.section_id)
        if key in seen:
            continue

        change_kind = change_kind_by_key.get(key)
        section = index.sections.get(verdict.section_id)
        if change_kind is None or section is None:
            continue
        seen.add(key)

        file, qualified_name = verdict.symbol_id.split("::", 1)
        symbol_name = qualified_name.rsplit(".", 1)[-1]
        fc = by_path.get(file)
        new_code = extract_symbol_source(fc.new_content if fc else None, file, qualified_name)

        inputs.append(
            RepairInput(
                symbol_id=verdict.symbol_id,
                section_id=verdict.section_id,
                file=section.file,
                change_kind=change_kind,
                symbol_name=symbol_name,
                new_code=new_code,
                section_text=section.raw,
                reason=verdict.reason,
                wrong_claims=verdict.wrong_claims,
                verdict_confidence=verdict.confidence,
            )
        )

    return inputs


def repair_pr(
    repo_root: str,
    base: str,
    head: str,
    index_path: str,
    settings: Settings,
    client: LLMClient,
) -> RepairResult:
    """Run detection, investigation, and repair end-to-end for a base/head diff.

    Re-composes the detection and investigation stages directly (rather than calling
    ``investigate_pr``, whose return value discards the suspects and file changes that
    repair-input assembly needs), keeps only the stale verdicts, then for each one
    rewrites the section, validates the rewrite (when it changed), and routes it.

    Args:
        repo_root: Path to the git working tree.
        base: Base ref (old revision).
        head: Head ref (new revision).
        index_path: Filesystem path to the persisted index JSON.
        settings: Configuration for detection and repair routing.
        client: The LLM client used for both the investigation and repair calls.

    Returns:
        A RepairResult with one RepairOutcome per processed stale section, plus skip
        counts for sections whose repair or validation reply was malformed.

    Raises:
        RuntimeError: If the backend is unavailable (propagated from the LLM client).
    """
    detection, file_changes = run_detection(repo_root, base, head, index_path, settings)
    index = load_index(index_path)

    inv_inputs = build_investigation_inputs(detection.suspects, file_changes, index)
    inv_result = investigate(inv_inputs, client)
    stale = [v for v in inv_result.verdicts if v.stale]
    verified = sum(1 for v in inv_result.verdicts if not v.stale)

    repair_inputs = build_repair_inputs(stale, detection.suspects, file_changes, index)

    result = RepairResult(verified=verified)
    for inp in repair_inputs:
        try:
            proposal = repair_section(inp, client)
        except (ValueError, KeyError, TypeError) as exc:
            result.skipped["repair_error"] = result.skipped.get("repair_error", 0) + 1
            logger.warning("Skipping repair for section=%s: %s", inp.section_id, exc)
            continue

        validation = None
        if proposal.changed:
            try:
                validation = validate_repair(inp, proposal, client)
            except (ValueError, KeyError, TypeError) as exc:
                result.skipped["validation_error"] = (
                    result.skipped.get("validation_error", 0) + 1
                )
                logger.warning("Skipping validation for section=%s: %s", inp.section_id, exc)
                continue

        route_result, reason = route(
            proposal, validation, inp.change_kind, inp.verdict_confidence, settings
        )
        result.outcomes.append(
            RepairOutcome(
                proposal=proposal, validation=validation, route=route_result, reason=reason
            )
        )

    return result
