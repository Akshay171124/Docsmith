"""Prompt templates for staleness verification, repair, and validation."""

from __future__ import annotations

from src.detection.models import InvestigationInput

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
