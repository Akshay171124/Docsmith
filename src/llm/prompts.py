"""Prompt templates for staleness verification, repair, and validation."""

from __future__ import annotations

from src.detection.models import InvestigationInput, RepairInput, RepairProposal

SYSTEM_PROMPT = """\
You are a precise, conservative technical-documentation reviewer.

You will be shown a code symbol that changed between two revisions, and a section
of documentation that references (or may reference) that symbol. Your job is to
decide whether the documentation section is now STALE: that is, whether the code
change makes a concrete, factual claim in the doc section wrong.

Rules:
- Be conservative. Only flag a doc section as stale when a specific claim it makes
  (about a function's name, parameters, return value, behavior, or existence) is
  now factually contradicted by the code change. Do not flag speculative,
  stylistic, or vague concerns.
- If a symbol the doc section describes was renamed, removed, or had its
  signature changed (parameters added/removed/reordered/retyped), and the doc
  still describes the old name or signature, treat that as stale.
- If the change is a behavior-neutral refactor (e.g. internal implementation
  changed but the public signature, name, and observable behavior are the same),
  treat the doc section as NOT stale.
- When in doubt, prefer NOT stale over stale, and lower confidence over higher
  confidence.

Respond with a single structured verdict containing:
- stale: whether the documentation section is now factually wrong (boolean).
- confidence: your confidence in this verdict, from 0.0 to 1.0.
- reason: a short, specific explanation for the verdict.
- wrong_claims: the specific claims in the doc section that are no longer
  accurate (empty if not stale).
"""

VERDICT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "stale": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "wrong_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stale", "confidence", "reason", "wrong_claims"],
    "additionalProperties": False,
}


def build_staleness_prompt(inp: InvestigationInput) -> str:
    """Render the user prompt for a single symbol/doc-section staleness check.

    Args:
        inp: The symbol change and doc section under investigation.

    Returns:
        A prompt string with clearly delimited sections for the change kind,
        symbol name, old/new code, and doc section text.
    """
    old_code_block = (
        inp.old_code if inp.old_code is not None else "(no previous version — symbol was added)"
    )
    new_code_block = (
        inp.new_code if inp.new_code is not None else "(no new version — symbol was removed)"
    )

    return f"""\
## Change kind
{inp.change_kind.value}

## Symbol name
{inp.symbol_name}

## OLD code
```
{old_code_block}
```

## NEW code
```
{new_code_block}
```

## Documentation section
```
{inp.doc_section_text}
```

Decide whether the documentation section above is stale relative to the code
change, following the rules in the system prompt. Respond with the structured
verdict only.
"""


REPAIR_SYSTEM_PROMPT = """\
You are a precise technical-documentation editor.

You will be shown a documentation section that is STALE, the current source code
of the symbol it describes, and a diagnosis of what is now wrong. Rewrite the
section so it is accurate for the new code.

Rules:
- Change ONLY what the diagnosis says is wrong. Preserve everything else exactly:
  wording, tone, structure, headings, formatting, and any correct details.
- Do not add new sections, examples, or commentary that were not there before.
- Keep the same voice and length unless a correction requires otherwise.
- If nothing actually needs to change, return the section unchanged.

Respond with a single field, revised_text: the full corrected section text.
"""

REPAIR_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "revised_text": {"type": "string"},
    },
    "required": ["revised_text"],
    "additionalProperties": False,
}


def build_repair_prompt(inp: RepairInput) -> str:
    """Render the user prompt asking the LLM to rewrite a stale doc section.

    Args:
        inp: The repair input bundle (section text, new code, diagnosis).

    Returns:
        A prompt string containing the diagnosis, the new code, and the current
        section text in clearly delimited blocks. Contains the word "Rewrite".
    """
    new_code = inp.new_code if inp.new_code is not None else "(the symbol no longer exists)"
    wrong = "\n".join(f"- {c}" for c in inp.wrong_claims) or "- (none listed)"
    return (
        f"Rewrite the documentation section below so it is accurate.\n\n"
        f"Symbol: {inp.symbol_name} ({inp.change_kind.value})\n\n"
        f"Diagnosis (why it is stale):\n{inp.reason}\n\n"
        f"Specific wrong claims:\n{wrong}\n\n"
        f"--- NEW CODE ---\n{new_code}\n--- END NEW CODE ---\n\n"
        f"--- CURRENT SECTION ---\n{inp.section_text}\n--- END CURRENT SECTION ---\n"
    )


VALIDATE_SYSTEM_PROMPT = """\
You are a careful reviewer checking a proposed revision of a documentation section.

You will be shown the ORIGINAL section, a PROPOSED REVISION, the current source
code, and the diagnosis that prompted the change. Judge three things:
- accurate: does the proposed revision correctly describe the new code?
- preserved: were the parts that were already correct kept intact (nothing correct
  was dropped, and nothing unrelated was rewritten)?
- style_ok: is the tone, structure, and formatting consistent with the original?

Be strict: if you are unsure on any axis, mark it false. Respond with the three
booleans and a short notes string.
"""

VALIDATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "accurate": {"type": "boolean"},
        "preserved": {"type": "boolean"},
        "style_ok": {"type": "boolean"},
        "notes": {"type": "string"},
    },
    "required": ["accurate", "preserved", "style_ok", "notes"],
    "additionalProperties": False,
}


def build_validate_prompt(inp: RepairInput, proposal: RepairProposal) -> str:
    """Render the user prompt asking the LLM to validate a repair proposal.

    Args:
        inp: The repair input bundle (for the new code and diagnosis).
        proposal: The proposed rewrite to validate.

    Returns:
        A prompt string containing the original section, the proposed revision, the
        new code, and the diagnosis. Contains the phrase "proposed revision".
    """
    new_code = inp.new_code if inp.new_code is not None else "(the symbol no longer exists)"
    return (
        f"Review the proposed revision below.\n\n"
        f"Symbol: {inp.symbol_name} ({inp.change_kind.value})\n\n"
        f"Diagnosis:\n{inp.reason}\n\n"
        f"--- NEW CODE ---\n{new_code}\n--- END NEW CODE ---\n\n"
        f"--- ORIGINAL SECTION ---\n{proposal.original_text}\n--- END ORIGINAL SECTION ---\n\n"
        f"--- PROPOSED REVISION ---\n{proposal.revised_text}\n--- END PROPOSED REVISION ---\n"
    )
