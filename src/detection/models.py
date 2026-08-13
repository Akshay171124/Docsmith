"""Data models for the change-detection stage: symbol-level diffs and doc suspects."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ChangeKind(enum.Enum):
    """The way a code symbol differs between two revisions.

    Attributes:
        ADDED: The symbol did not exist in the old revision.
        REMOVED: The symbol existed in the old revision but is absent from the new one.
        SIGNATURE_CHANGED: The symbol's signature (parameters/return type) changed; its
            body may have changed too.
        BODY_CHANGED: Only the symbol's body changed; its signature is unchanged.
    """

    ADDED = "added"
    REMOVED = "removed"
    SIGNATURE_CHANGED = "signature_changed"
    BODY_CHANGED = "body_changed"


@dataclass(frozen=True)
class FileChange:
    """A single file's diff between two revisions, as fed to symbol-level diffing.

    Attributes:
        path: Repo-relative path of the file.
        old_content: File contents before the change, or ``None`` if the file is new.
        new_content: File contents after the change, or ``None`` if the file was deleted.
        changed_lines: New-file line numbers that were added or modified by the diff.
    """

    path: str
    old_content: str | None
    new_content: str | None
    changed_lines: frozenset[int]


@dataclass(frozen=True)
class ChangedSymbol:
    """A code symbol whose definition changed between two revisions.

    Attributes:
        id: Symbol identifier as ``"{file}::{qualified_name}"``, matching the index's
            ``Symbol.id`` scheme.
        name: Unqualified symbol name.
        qualified_name: Fully qualified name (e.g. including an enclosing class).
        file: Repo-relative path of the file defining the symbol.
        kind: How the symbol changed.
        start_line: Start of the symbol's span in the new revision, or in the old
            revision when ``kind`` is ``ChangeKind.REMOVED``.
        end_line: End of the symbol's span, using the same old/new convention as
            ``start_line``.
        old_signature: Signature before the change, or ``None`` if the symbol had no
            prior signature (e.g. ``ADDED``).
        new_signature: Signature after the change, or ``None`` if the symbol no longer
            exists (e.g. ``REMOVED``).
    """

    id: str
    name: str
    qualified_name: str
    file: str
    kind: ChangeKind
    start_line: int
    end_line: int
    old_signature: str | None
    new_signature: str | None


@dataclass(frozen=True)
class Suspect:
    """A candidate link between a changed symbol and a doc section that may be stale.

    Attributes:
        symbol_id: ``ChangedSymbol.id`` of the symbol implicated in the change.
        section_id: Identifier of the documentation section suspected of referencing it.
        change_kind: The kind of change made to the underlying symbol.
        via: How the link was discovered: ``"index-link"`` when matched through
            ``index.links``, or ``"name-reference"`` when the doc section names the
            symbol directly.
    """

    symbol_id: str
    section_id: str
    change_kind: ChangeKind
    via: str


@dataclass(frozen=True)
class Verdict:
    """The investigator's judgment on whether a doc section is stale for a symbol.

    Attributes:
        symbol_id: ``ChangedSymbol.id`` of the symbol under investigation.
        section_id: Identifier of the documentation section being judged.
        stale: Whether the doc section is stale relative to the symbol's current state.
        confidence: The investigator's confidence in ``stale``, from 0.0 to 1.0.
        reason: Human-readable explanation for the verdict.
        wrong_claims: Specific claims in the doc section that are no longer accurate.
    """

    symbol_id: str
    section_id: str
    stale: bool
    confidence: float
    reason: str
    wrong_claims: tuple[str, ...]


@dataclass(frozen=True)
class InvestigationInput:
    """The evidence handed to the investigator for a single symbol/section pairing.

    Attributes:
        symbol_id: ``ChangedSymbol.id`` of the symbol under investigation.
        section_id: Identifier of the documentation section being judged.
        change_kind: The kind of change made to the underlying symbol.
        symbol_name: Unqualified name of the symbol.
        old_code: Symbol source before the change, or ``None`` if it did not exist
            (e.g. ``ChangeKind.ADDED``).
        new_code: Symbol source after the change, or ``None`` if it no longer exists
            (e.g. ``ChangeKind.REMOVED``).
        doc_section_text: Full text of the documentation section being judged.
    """

    symbol_id: str
    section_id: str
    change_kind: ChangeKind
    symbol_name: str
    old_code: str | None
    new_code: str | None
    doc_section_text: str


@dataclass
class InvestigationResult:
    """Aggregate output of the investigation stage for a batch of suspects.

    Attributes:
        verdicts: All verdicts produced by the investigator.
        skipped: Counts of suspects excluded from investigation, keyed by the reason
            they were skipped.
    """

    verdicts: list[Verdict] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)


@dataclass
class DetectionResult:
    """Aggregate output of the detection stage for a single diff.

    Attributes:
        changed_symbols: All symbols found to have changed.
        suspects: Candidate symbol-to-doc-section links surfaced for further triage.
        dropped: Counts of changed symbols excluded from ``suspects``, keyed by the
            reason they were dropped.
    """

    changed_symbols: list[ChangedSymbol] = field(default_factory=list)
    suspects: list[Suspect] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
