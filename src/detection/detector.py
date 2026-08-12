"""Detection orchestrator: compose the deterministic detection pipeline end-to-end."""

from __future__ import annotations

from src.detection.candidate_linker import find_suspects
from src.detection.git_adapter import collect_changes
from src.detection.models import DetectionResult
from src.detection.symbol_mapper import map_changes
from src.detection.triage_filter import triage
from src.index.store import load_index
from src.utils.config import Settings


def detect(
    repo_root: str, base: str, head: str, index_path: str, settings: Settings
) -> DetectionResult:
    """Run the full deterministic detection pipeline for a base/head diff.

    Composes the existing detection stages: collects file-level changes from git,
    maps them to changed code symbols, triages out noise, loads the persisted
    index, and links the surviving symbols to candidate stale doc sections.

    Args:
        repo_root: Path to the git working tree.
        base: Base ref (old revision).
        head: Head ref (new revision).
        index_path: Filesystem path to the persisted index JSON.
        settings: Triage configuration.

    Returns:
        A DetectionResult with the triaged changed symbols, linked suspects, and
        drop counts keyed by reason (including ``"no_candidates"`` for symbols
        that survived triage but produced no suspects).
    """
    file_changes = collect_changes(repo_root, base, head)
    changed_symbols = map_changes(file_changes)
    kept, dropped = triage(changed_symbols, file_changes, settings)

    index = load_index(index_path)
    suspects = find_suspects(kept, index)

    symbol_ids_with_suspects = {suspect.symbol_id for suspect in suspects}
    no_candidates = sum(1 for symbol in kept if symbol.id not in symbol_ids_with_suspects)
    if no_candidates > 0:
        dropped["no_candidates"] = no_candidates

    return DetectionResult(changed_symbols=kept, suspects=suspects, dropped=dropped)
