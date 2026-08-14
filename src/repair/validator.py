"""Stage 7: independent LLM quality gate (accuracy, preservation, style)."""

from __future__ import annotations

from src.detection.models import RepairInput, RepairProposal, ValidationResult
from src.llm.client import LLMClient
from src.llm.prompts import VALIDATE_SYSTEM_PROMPT, VALIDATION_SCHEMA, build_validate_prompt

_REQUIRED = ("accurate", "preserved", "style_ok", "notes")


def _parse_validation(raw: dict) -> ValidationResult:
    """Validate a raw validation response into a ValidationResult.

    Args:
        raw: The decoded JSON object returned by the LLM.

    Returns:
        A ValidationResult.

    Raises:
        ValueError: If a required key is missing or a field has the wrong type.
    """
    for key in _REQUIRED:
        if key not in raw:
            raise ValueError(f"validation response missing '{key}'")
    for key in ("accurate", "preserved", "style_ok"):
        if not isinstance(raw[key], bool):
            raise ValueError(f"validation field '{key}' must be a boolean")
    if not isinstance(raw["notes"], str):
        raise ValueError("validation field 'notes' must be a string")
    return ValidationResult(
        accurate=raw["accurate"],
        preserved=raw["preserved"],
        style_ok=raw["style_ok"],
        notes=raw["notes"],
    )


def validate_repair(
    inp: RepairInput, proposal: RepairProposal, client: LLMClient
) -> ValidationResult:
    """Independently judge a repair proposal for accuracy, preservation, and style.

    Args:
        inp: The repair input bundle (for the new code and diagnosis).
        proposal: The proposed rewrite to validate.
        client: The LLM client used to request the judgment.

    Returns:
        A ValidationResult with the three boolean flags and notes.

    Raises:
        ValueError: If the response is malformed (missing key or wrong field type).
    """
    raw = client.complete_json(
        VALIDATE_SYSTEM_PROMPT, build_validate_prompt(inp, proposal), VALIDATION_SCHEMA
    )
    return _parse_validation(raw)
