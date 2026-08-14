"""Repair orchestration: assemble inputs and run repair->validate->route per section."""

from __future__ import annotations

import logging

from src.detection.models import (
    FileChange,
    RepairInput,
    Suspect,
    Verdict,
)
from src.detection.source import extract_symbol_source
from src.models import Index

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
