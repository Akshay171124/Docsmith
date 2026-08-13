"""Stage 5: LLM staleness investigator with read_file/grep tools; confirms staleness + diagnosis."""

from __future__ import annotations

import logging

from src.detection.models import (
    FileChange,
    InvestigationInput,
    InvestigationResult,
    Suspect,
    Verdict,
)
from src.llm.client import LLMClient
from src.llm.prompts import SYSTEM_PROMPT, VERDICT_SCHEMA, build_staleness_prompt
from src.models import Index
from src.parsing.code_parser import parse_source
from src.parsing.languages import language_for_path

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
        old_code = _extract_source(fc.old_content if fc else None, file, qualified_name)
        new_code = _extract_source(fc.new_content if fc else None, file, qualified_name)

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


def _extract_source(content: str | None, file: str, qualified_name: str) -> str | None:
    """Extract a symbol's source text from full file content by re-parsing.

    Args:
        content: Full file content, or None if the file didn't exist at this revision.
        file: Repo-relative path of the file (used to resolve the language).
        qualified_name: Fully qualified name of the symbol to extract.

    Returns:
        The symbol's source lines (1-based, inclusive), or None if `content` is
        None, the language is unsupported, or the symbol isn't found.
    """
    if content is None:
        return None

    language = language_for_path(file)
    if language is None:
        return None

    symbols = parse_source(content, file, language)
    symbol = next((s for s in symbols if s.qualified_name == qualified_name), None)
    if symbol is None:
        return None

    lines = content.splitlines()
    return "\n".join(lines[symbol.start_line - 1 : symbol.end_line])


def investigate(inputs: list[InvestigationInput], client: LLMClient) -> InvestigationResult:
    """Ask the LLM to judge staleness for each investigation input.

    Args:
        inputs: One evidence bundle per symbol/doc-section pairing to judge.
        client: The LLM client used to request each staleness verdict.

    Returns:
        An `InvestigationResult` with one `Verdict` per input that produced a valid,
        well-shaped response. Inputs whose LLM call raises or whose response fails
        validation are counted under `skipped["llm_error"]` rather than aborting the
        batch.
    """
    result = InvestigationResult()

    for inp in inputs:
        try:
            raw = client.complete_json(SYSTEM_PROMPT, build_staleness_prompt(inp), VERDICT_SCHEMA)
            verdict = _parse_verdict(raw, inp)
        except Exception as exc:  # noqa: BLE001 - one bad input must not abort the batch
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
