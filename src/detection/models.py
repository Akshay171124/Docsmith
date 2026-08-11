from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ChangeKind(enum.Enum):
    ADDED = "added"
    REMOVED = "removed"
    SIGNATURE_CHANGED = "signature_changed"
    BODY_CHANGED = "body_changed"


@dataclass(frozen=True)
class FileChange:
    path: str
    old_content: str | None
    new_content: str | None
    changed_lines: frozenset[int]


@dataclass(frozen=True)
class ChangedSymbol:
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
    symbol_id: str
    section_id: str
    change_kind: ChangeKind
    via: str


@dataclass
class DetectionResult:
    changed_symbols: list[ChangedSymbol] = field(default_factory=list)
    suspects: list[Suspect] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
