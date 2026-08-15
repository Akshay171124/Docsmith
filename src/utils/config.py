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
        llm_backend: Which LLM backend the investigator uses (`fake`, `ollama`, `claude`).
        ollama_model: Model name to request from the Ollama backend.
        ollama_host: Base URL of the Ollama server.
        claude_model: Model name to request from the Claude backend.
        repair_confidence_threshold: Min investigator confidence for an AUTOFIX route.
        repair_autofix_change_kinds: Change kinds eligible for AUTOFIX (by ChangeKind value).
    """

    ignore_paths: list[str] = field(default_factory=list)
    doc_ignore: list[str] = field(default_factory=list)
    skip_comment_only: bool = True
    skip_whitespace_only: bool = True
    llm_backend: str = "ollama"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_host: str = "http://localhost:11434"
    claude_model: str = "claude-sonnet-5"
    repair_confidence_threshold: float = 0.8
    repair_autofix_change_kinds: tuple[str, ...] = ("signature_changed",)


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
    llm = raw.get("llm") or {}
    repair = raw.get("repair") or {}

    skip_comment_only = triage.get("skip_comment_only", True)
    if skip_comment_only is None:
        skip_comment_only = True

    skip_whitespace_only = triage.get("skip_whitespace_only", True)
    if skip_whitespace_only is None:
        skip_whitespace_only = True

    settings = Settings(
        ignore_paths=triage.get("ignore_paths") or [],
        doc_ignore=docs.get("ignore") or [],
        skip_comment_only=skip_comment_only,
        skip_whitespace_only=skip_whitespace_only,
        llm_backend=llm.get("backend") or "ollama",
        ollama_model=llm.get("ollama_model") or "qwen2.5-coder:7b",
        ollama_host=llm.get("ollama_host") or "http://localhost:11434",
        claude_model=llm.get("claude_model") or "claude-sonnet-5",
        repair_confidence_threshold=(
            repair.get("confidence_threshold")
            if repair.get("confidence_threshold") is not None
            else 0.8
        ),
        repair_autofix_change_kinds=tuple(
            repair.get("autofix_change_kinds") or ["signature_changed"]
        ),
    )

    if overrides:
        for key, value in overrides.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

    return settings
