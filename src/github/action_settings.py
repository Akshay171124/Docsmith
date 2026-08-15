"""Merge GitHub Action inputs (INPUT_* env vars) into a Settings object."""

from __future__ import annotations

from collections.abc import Mapping

from src.utils.config import Settings, load_settings


def settings_from_env(env: Mapping[str, str]) -> Settings:
    """Build Settings from a base config plus GitHub Action input env vars.

    Reads ``INPUT_LLM-BACKEND``, ``INPUT_OLLAMA-HOST``, ``INPUT_CONFIDENCE-THRESHOLD``,
    ``INPUT_AUTO-FIX``, and ``INPUT_IGNORE-GLOBS`` when present, overriding the base
    config. (``doc-globs`` is accepted by the Action but not yet consumed by index
    discovery.)

    Args:
        env: Environment mapping with Action inputs.

    Returns:
        A populated Settings.
    """
    settings = load_settings(env.get("INPUT_CONFIG") or "configs/base.yaml")

    backend = env.get("INPUT_LLM-BACKEND")
    if backend:
        settings.llm_backend = backend

    host = env.get("INPUT_OLLAMA-HOST")
    if host:
        settings.ollama_host = host

    threshold = env.get("INPUT_CONFIDENCE-THRESHOLD")
    if threshold:
        settings.repair_confidence_threshold = float(threshold)

    auto_fix = env.get("INPUT_AUTO-FIX")
    if auto_fix not in (None, ""):
        settings.auto_fix = auto_fix.strip().lower() == "true"

    ignore = env.get("INPUT_IGNORE-GLOBS")
    if ignore:
        settings.doc_ignore = [g.strip() for g in ignore.split(",") if g.strip()]

    return settings
