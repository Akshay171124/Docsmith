"""Load and merge layered YAML config (base.yaml + overrides + action inputs)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Settings:
    """Flat view of the Docsmith configuration used by the detection pipeline.

    Attributes:
        ignore_paths: Glob patterns for paths the triage stage should skip.
        doc_ignore: Glob patterns for doc files to exclude from monitoring.
        skip_comment_only: Drop diff hunks that contain only comment changes.
        skip_whitespace_only: Drop diff hunks that contain only whitespace changes.
    """

    ignore_paths: list[str] = field(default_factory=list)
    doc_ignore: list[str] = field(default_factory=list)
    skip_comment_only: bool = True
    skip_whitespace_only: bool = True


def load_settings(
    path: str = "configs/base.yaml",
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """Load a Settings object from a YAML config file with optional overrides.

    Missing ``triage`` or ``docs`` sections are silently treated as empty; each
    field falls back to its default value.  ``overrides`` is a flat dict whose
    keys must match ``Settings`` field names; matching keys shallow-replace the
    loaded values.

    Args:
        path: Filesystem path to the YAML config file.
        overrides: Optional flat dict of field-name → value pairs that take
            precedence over the loaded config.

    Returns:
        A populated ``Settings`` instance.
    """
    with open(path) as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    triage = raw.get("triage") or {}
    docs = raw.get("docs") or {}

    settings = Settings(
        ignore_paths=triage.get("ignore_paths", []),
        doc_ignore=docs.get("ignore", []),
        skip_comment_only=triage.get("skip_comment_only", True),
        skip_whitespace_only=triage.get("skip_whitespace_only", True),
    )

    if overrides:
        for key, value in overrides.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

    return settings
