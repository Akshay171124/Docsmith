"""Stage 5: LLM staleness investigator with read_file/grep tools; confirms staleness + diagnosis."""

from __future__ import annotations

import logging

from src.detection.detector import run_detection
from src.detection.models import (
    FileChange,
    InvestigationInput,
    InvestigationResult,
    Suspect,
    Verdict,
)
from src.detection.source import extract_symbol_source
from src.index.store import load_index
from src.llm.client import ClaudeClient, FakeLLMClient, LLMClient, OllamaClient
from src.llm.prompts import SYSTEM_PROMPT, VERDICT_SCHEMA, build_staleness_prompt
from src.models import Index
from src.utils.config import Settings

logger = logging.getLogger(__name__)


def build_investigation_inputs(
    suspects: list[Suspect],
    file_changes: list[FileChange],
    index: Index,
) -> list[InvestigationInput]:
    """Assemble per-suspect investigation inputs from detection output.

    Args:
        suspects: Candidate symbol-to-doc-section links surfaced by detection.
        file_changes: The diffs the suspects were derived from.
        index: The current index, used to resolve doc section text.

    Returns:
        One `InvestigationInput` per unique `(symbol_id, section_id)` pair, in the
        order suspects were first seen. Suspects whose section is missing from the
        index are skipped.
    """
    by_path = {fc.path: fc for fc in file_changes}
    seen: set[tuple[str, str]] = set()
    inputs: list[InvestigationInput] = []

    for suspect in suspects:
        key = (suspect.symbol_id, suspect.section_id)
        if key in seen:
            continue

        section = index.sections.get(suspect.section_id)
        if section is None:
            continue
        seen.add(key)

        file, qualified_name = suspect.symbol_id.split("::", 1)
        symbol_name = qualified_name.rsplit(".", 1)[-1]

        fc = by_path.get(file)
        old_code = extract_symbol_source(fc.old_content if fc else None, file, qualified_name)
        new_code = extract_symbol_source(fc.new_content if fc else None, file, qualified_name)

        inputs.append(
            InvestigationInput(
                symbol_id=suspect.symbol_id,
                section_id=suspect.section_id,
                change_kind=suspect.change_kind,
                symbol_name=symbol_name,
                old_code=old_code,
                new_code=new_code,
                doc_section_text=section.raw,
            )
        )

    return inputs


def investigate(inputs: list[InvestigationInput], client: LLMClient) -> InvestigationResult:
    """Ask the LLM to judge staleness for each investigation input.

    Args:
        inputs: One evidence bundle per symbol/doc-section pairing to judge.
        client: The LLM client used to request each staleness verdict.

    Returns:
        An `InvestigationResult` with one `Verdict` per input that produced a valid,
        well-shaped response. Inputs whose response is malformed or fails validation
        (`ValueError`, `KeyError`, `TypeError` — including `json.JSONDecodeError`,
        a `ValueError` subclass, from a responding backend that returns non-JSON
        content) are counted under `skipped["llm_error"]` rather than aborting the
        batch. A backend-unavailable `RuntimeError` (e.g. Ollama unreachable, or a
        missing Claude API key) is NOT caught here: it propagates out of this
        function and aborts the batch, since every remaining suspect would fail
        identically.
    """
    result = InvestigationResult()

    for inp in inputs:
        try:
            raw = client.complete_json(SYSTEM_PROMPT, build_staleness_prompt(inp), VERDICT_SCHEMA)
            verdict = _parse_verdict(raw, inp)
        except (ValueError, KeyError, TypeError) as exc:
            result.skipped["llm_error"] = result.skipped.get("llm_error", 0) + 1
            logger.warning(
                "Skipping investigation for symbol=%s section=%s: %s",
                inp.symbol_id,
                inp.section_id,
                exc,
            )
            continue

        result.verdicts.append(verdict)

    return result


def _parse_verdict(raw: dict, inp: InvestigationInput) -> Verdict:
    """Validate and convert a raw LLM response into a `Verdict`.

    Args:
        raw: The parsed JSON response from the LLM client.
        inp: The investigation input the response corresponds to.

    Returns:
        A `Verdict` built from `raw`, tagged with `inp`'s symbol/section ids.

    Raises:
        ValueError: If `raw` is not a dict, is missing a required key, or has a
            key of the wrong type.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"expected dict response, got {type(raw).__name__}")

    for key in ("stale", "confidence", "reason", "wrong_claims"):
        if key not in raw:
            raise ValueError(f"missing required key: {key!r}")

    stale = raw["stale"]
    if not isinstance(stale, bool):
        raise ValueError(f"'stale' must be bool, got {type(stale).__name__}")

    confidence = raw["confidence"]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError(f"'confidence' must be int/float, got {type(confidence).__name__}")

    reason = raw["reason"]
    if not isinstance(reason, str):
        raise ValueError(f"'reason' must be str, got {type(reason).__name__}")

    wrong_claims = raw["wrong_claims"]
    if not isinstance(wrong_claims, list) or not all(isinstance(c, str) for c in wrong_claims):
        raise ValueError("'wrong_claims' must be a list of str")

    return Verdict(
        symbol_id=inp.symbol_id,
        section_id=inp.section_id,
        stale=stale,
        confidence=float(confidence),
        reason=reason,
        wrong_claims=tuple(wrong_claims),
    )


def investigate_pr(
    repo_root: str,
    base: str,
    head: str,
    index_path: str,
    settings: Settings,
    client: LLMClient,
) -> InvestigationResult:
    """Run detection and investigation end-to-end for a base/head diff.

    Composes the deterministic detection pipeline with the LLM investigator:
    runs detection to find suspect doc sections, assembles evidence bundles for
    each suspect, and asks the LLM client to judge staleness for each one.

    Args:
        repo_root: Path to the git working tree.
        base: Base ref (old revision).
        head: Head ref (new revision).
        index_path: Filesystem path to the persisted index JSON.
        settings: Triage configuration used by the detection stage.
        client: The LLM client used to request each staleness verdict.

    Returns:
        An `InvestigationResult` with one `Verdict` per suspect that produced a
        valid response, plus skip counts for suspects the investigator couldn't
        judge.
    """
    result, file_changes = run_detection(repo_root, base, head, index_path, settings)
    index = load_index(index_path)
    inputs = build_investigation_inputs(result.suspects, file_changes, index)
    return investigate(inputs, client)


def make_client(settings: Settings, backend_override: str | None = None) -> LLMClient:
    """Construct the LLM client indicated by settings (or an explicit override).

    Args:
        settings: Configuration providing the default backend and per-backend
            model/host fields.
        backend_override: If given, takes precedence over `settings.llm_backend`.

    Returns:
        An `LLMClient` for the selected backend.

    Raises:
        ValueError: If the selected backend name is not one of `"ollama"`,
            `"claude"`, or `"fake"`.
    """
    backend = backend_override or settings.llm_backend

    if backend == "ollama":
        return OllamaClient(settings.ollama_model, settings.ollama_host)
    if backend == "claude":
        return ClaudeClient(settings.claude_model)
    if backend == "fake":
        # Offline stand-in for CLI smoke tests only: scripted to always report
        # staleness so `docsmith investigate --backend fake` demonstrably works
        # without a real LLM backend.
        return FakeLLMClient(
            {
                "stale": True,
                "confidence": 0.9,
                "reason": "fake",
                "wrong_claims": [],
            }
        )

    raise ValueError(f"Unknown LLM backend: {backend!r} (expected 'ollama', 'claude', or 'fake')")
