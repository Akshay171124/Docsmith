"""Stage 6: rewrite only the stale spans, preserving tone and structure."""

from __future__ import annotations

import difflib

from src.detection.models import RepairInput, RepairProposal
from src.llm.client import LLMClient
from src.llm.prompts import REPAIR_SCHEMA, REPAIR_SYSTEM_PROMPT, build_repair_prompt


def _unified_diff(original: str, revised: str, file: str) -> str:
    """Compute a unified diff of two texts, labelled with the doc file path."""
    lines = difflib.unified_diff(
        original.splitlines(),
        revised.splitlines(),
        fromfile=f"a/{file}",
        tofile=f"b/{file}",
        lineterm="",
    )
    return "\n".join(lines)


def repair_section(inp: RepairInput, client: LLMClient) -> RepairProposal:
    """Ask the LLM to rewrite a stale doc section, and diff the result.

    Args:
        inp: The repair input bundle (section text, new code, diagnosis).
        client: The LLM client used to request the rewrite.

    Returns:
        A RepairProposal with the revised text, a deterministic unified diff, and a
        ``changed`` flag (False when the rewrite is identical ignoring surrounding
        whitespace, in which case ``diff`` is "").

    Raises:
        ValueError: If the response is missing ``revised_text`` or it is not a string.
    """
    raw = client.complete_json(REPAIR_SYSTEM_PROMPT, build_repair_prompt(inp), REPAIR_SCHEMA)

    if "revised_text" not in raw:
        raise ValueError("repair response missing 'revised_text'")
    revised = raw["revised_text"]
    if not isinstance(revised, str):
        raise ValueError("repair response 'revised_text' must be a string")

    changed = revised.strip() != inp.section_text.strip()
    diff = _unified_diff(inp.section_text, revised, inp.file) if changed else ""

    return RepairProposal(
        symbol_id=inp.symbol_id,
        section_id=inp.section_id,
        file=inp.file,
        original_text=inp.section_text,
        revised_text=revised,
        diff=diff,
        changed=changed,
    )
