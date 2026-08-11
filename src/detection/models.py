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
