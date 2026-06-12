"""File content hashing and snapshot-diff utilities for incremental indexing."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Changes:
    """Result of diffing two ``{path: sha256}`` snapshots.

    Attributes:
        added: Paths present in current but absent from previous.
        changed: Paths in both snapshots whose hashes differ.
        deleted: Paths present in previous but absent from current.
    """

    added: set[str] = field(default_factory=set)
    changed: set[str] = field(default_factory=set)
    deleted: set[str] = field(default_factory=set)


def hash_file(path: str) -> str:
    """Return the SHA-256 hex digest of a file's raw bytes.

    Args:
        path: Absolute or relative path to the file to hash.

    Returns:
        A 64-character lowercase hexadecimal string.
    """
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def classify_changes(
    current: dict[str, str],
    previous: dict[str, str],
) -> Changes:
    """Classify path-level differences between two ``{path: sha256}`` maps.

    This is a pure function; it performs no filesystem access.

    Args:
        current: The latest snapshot mapping relative paths to SHA-256 digests.
        previous: The stored snapshot from the last index build.

    Returns:
        A :class:`Changes` instance with ``added``, ``changed``, and ``deleted``
        sets populated according to the diff between the two maps.
    """
    current_keys = set(current)
    previous_keys = set(previous)

    added = current_keys - previous_keys
    deleted = previous_keys - current_keys
    changed = {k for k in current_keys & previous_keys if current[k] != previous[k]}

    return Changes(added=added, changed=changed, deleted=deleted)
