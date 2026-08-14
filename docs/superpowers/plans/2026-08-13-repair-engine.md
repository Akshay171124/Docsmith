# Repair Engine (Week 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the investigator's stale `Verdict`s into routed doc corrections — rewrite each stale section, gate the rewrite with an independent LLM check, and route to AUTOFIX / FLAG / NO_CHANGE — behind the reused `LLMClient` seam, read-only, at $0.

**Architecture:** Three focused components (Repair Engine → Validator → Confidence Router) plus an orchestrator that re-composes the detection→investigation stages to retain the `suspects` + `FileChange`s repair needs. Whole-section LLM rewrite + a deterministic `difflib` diff; the router is pure/deterministic. A `docsmith repair` CLI and a free `make repair-demo` exercise it end-to-end.

**Tech Stack:** Python 3.11+, stdlib `difflib`, the existing `LLMClient` seam (Fake/Ollama/Claude), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-13-repair-engine-design.md`.

## Global Constraints

- **$0 cost posture (hard):** tests always use `FakeLLMClient` (offline, no key, in CI); the demo uses `OllamaClient` (free, local, default); `ClaudeClient` is optional/paid, never the default, never in the default suite. Importing any module must never import `anthropic`, open a socket, or need a key.
- **Reuse the seam:** all LLM calls go through `client.complete_json(system, user, schema) -> dict`. Two single-prompt structured calls per changed section (repair + validate). No agentic loop.
- **Error handling:** a per-section malformed/invalid LLM reply is skipped-and-counted (`RepairResult.skipped["repair_error"]` or `["validation_error"]`), never aborts the batch. Backend-unavailable `RuntimeError`s (Ollama down / missing key) **propagate** to the CLI boundary, which prints the message and exits non-zero — never silently counted. (Catch only `(ValueError, KeyError, TypeError)` in per-section loops.)
- **Repair mechanic:** whole-section rewrite; the diff is computed deterministically with `difflib.unified_diff` (never trusted from the LLM). `changed = revised.strip() != original.strip()`; `diff = ""` when unchanged.
- **Routing (deterministic):** `NO_CHANGE` when `not proposal.changed`. `AUTOFIX` iff `validation.accurate and validation.preserved and validation.style_ok` **and** `change_kind.value in settings.repair_autofix_change_kinds` (default `("signature_changed",)`) **and** `verdict_confidence >= settings.repair_confidence_threshold` (default `0.8`). Everything else `FLAG`.
- **Placement:** `RepairInput`, `RepairProposal`, `ValidationResult`, `RepairRoute`, `RepairOutcome`, `RepairResult` all live in `src/detection/models.py` (like `InvestigationInput`). Repair-stage code lives in `src/repair/` (the `repairer.py`/`validator.py`/`confidence_router.py` stubs are replaced; `engine.py` is new).
- **Prompt anchors:** `build_repair_prompt` output must contain the literal word `Rewrite`; `build_validate_prompt` output must contain the literal phrase `proposed revision`. These let the offline integration `FakeLLMClient` route each call type deterministically.
- ruff line-length 100; docstrings with Args/Returns/Raises; TDD (failing test first); frequent commits; **no LLM/AI attribution** in any commit (no `Co-Authored-By`, "Generated with", etc.). Do **not** edit `docs/planning/roadmap.md` or `CHANGELOG.md` — living docs are controller-managed.

---

## File Structure

- `src/utils/config.py` (modify) — add `repair_confidence_threshold`, `repair_autofix_change_kinds` to `Settings`; read a `repair:` block in `load_settings`.
- `configs/base.yaml` (modify) — add a `repair:` block.
- `src/detection/source.py` (create) — `extract_symbol_source(...)`, promoted from the investigator's private `_extract_source`; reused by both stages.
- `src/detection/investigator.py` (modify) — import the promoted helper instead of its local copy.
- `src/detection/models.py` (modify) — the six repair types.
- `src/llm/prompts.py` (modify) — repair + validation prompts and schemas.
- `src/repair/repairer.py` (replace stub) — `repair_section`.
- `src/repair/validator.py` (replace stub) — `validate_repair`.
- `src/repair/confidence_router.py` (replace stub) — `route`.
- `src/repair/engine.py` (create) — `build_repair_inputs`, `repair_pr`.
- `docsmith.py` (modify) — `repair` subcommand.
- `Makefile` (modify), `scripts/dev/repair_demo.sh` (create), `README.md` (modify), `tests/integration/test_repair_ollama.py` (create) — free demo + gated test.

---

## Task 0: Repair config settings

**Files:**
- Modify: `src/utils/config.py`
- Modify: `configs/base.yaml`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: existing `Settings` dataclass + `load_settings(path, overrides=None)`.
- Produces: `Settings.repair_confidence_threshold: float` (default `0.8`), `Settings.repair_autofix_change_kinds: tuple[str, ...]` (default `("signature_changed",)`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`:

```python
def test_load_settings_reads_repair_block(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "repair:\n"
        "  confidence_threshold: 0.6\n"
        "  autofix_change_kinds: [signature_changed, body_changed]\n"
    )
    s = load_settings(str(cfg))
    assert s.repair_confidence_threshold == 0.6
    assert s.repair_autofix_change_kinds == ("signature_changed", "body_changed")


def test_load_settings_repair_defaults(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("{}\n")
    s = load_settings(str(cfg))
    assert s.repair_confidence_threshold == 0.8
    assert s.repair_autofix_change_kinds == ("signature_changed",)
```

(Ensure `from src.utils.config import load_settings` is imported at the top of the test file — it already is if other config tests exist.)

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/unit/test_config.py -k repair -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'repair_confidence_threshold'`.

- [ ] **Step 3: Add the fields to `Settings`**

In `src/utils/config.py`, add these two fields at the end of the `Settings` dataclass (after `claude_model`):

```python
    repair_confidence_threshold: float = 0.8
    repair_autofix_change_kinds: tuple[str, ...] = ("signature_changed",)
```

And add matching lines to the `Settings` docstring Attributes section:

```python
        repair_confidence_threshold: Min investigator confidence for an AUTOFIX route.
        repair_autofix_change_kinds: Change kinds eligible for AUTOFIX (by ChangeKind value).
```

- [ ] **Step 4: Read the `repair:` block in `load_settings`**

In `src/utils/config.py` `load_settings`, after the `llm = raw.get("llm") or {}` line add:

```python
    repair = raw.get("repair") or {}
```

and in the `Settings(...)` constructor call, after `claude_model=...`, add:

```python
        repair_confidence_threshold=(
            repair.get("confidence_threshold")
            if repair.get("confidence_threshold") is not None
            else 0.8
        ),
        repair_autofix_change_kinds=tuple(
            repair.get("autofix_change_kinds") or ["signature_changed"]
        ),
```

- [ ] **Step 5: Add the `repair:` block to `configs/base.yaml`**

Append to `configs/base.yaml` (the top-level legacy `confidence_threshold`/`auto_fix` keys stay as-is; repair reads from this new block):

```yaml

# Repair (stage 8 routing).
repair:
  confidence_threshold: 0.8              # min investigator confidence for an AUTOFIX
  autofix_change_kinds: [signature_changed]   # change kinds eligible for AUTOFIX
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_config.py -v`
Expected: PASS (all config tests, including the two new ones).

- [ ] **Step 7: Commit**

```bash
git add src/utils/config.py configs/base.yaml tests/unit/test_config.py
git commit -m "feat: add repair routing settings to config"
```

---

## Task 1: Promote the symbol-source extractor to a shared helper

**Files:**
- Create: `src/detection/source.py`
- Modify: `src/detection/investigator.py`
- Test: `tests/unit/test_source.py`

**Interfaces:**
- Consumes: `parse_source` (`src/parsing/code_parser.py`), `language_for_path` (`src/parsing/languages.py`).
- Produces: `extract_symbol_source(content: str | None, file: str, qualified_name: str) -> str | None` — identical behavior to the investigator's current private `_extract_source`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_source.py`:

```python
from src.detection.source import extract_symbol_source

PY = '''\
def alpha(x):
    return x


def beta(y, z):
    return y + z
'''


def test_extracts_named_symbol_source():
    src = extract_symbol_source(PY, "m.py", "beta")
    assert src == "def beta(y, z):\n    return y + z"


def test_returns_none_when_content_is_none():
    assert extract_symbol_source(None, "m.py", "beta") is None


def test_returns_none_for_unknown_symbol():
    assert extract_symbol_source(PY, "m.py", "gamma") is None


def test_returns_none_for_unsupported_language():
    assert extract_symbol_source("whatever", "notes.txt", "beta") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.detection.source'`.

- [ ] **Step 3: Create the shared helper**

Create `src/detection/source.py`:

```python
"""Extract a code symbol's source text from in-memory file content.

Shared by the staleness investigator and the repair engine so both slice a
changed symbol's source the same way.
"""

from __future__ import annotations

from src.parsing.code_parser import parse_source
from src.parsing.languages import language_for_path


def extract_symbol_source(content: str | None, file: str, qualified_name: str) -> str | None:
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
```

- [ ] **Step 4: Point the investigator at the shared helper**

In `src/detection/investigator.py`: delete the local `def _extract_source(...)` function entirely. Remove the now-unused imports `from src.parsing.code_parser import parse_source` and `from src.parsing.languages import language_for_path` **only if** nothing else in the file uses them (check with grep; the investigator used them solely for `_extract_source`). Add:

```python
from src.detection.source import extract_symbol_source
```

Then in `build_investigation_inputs`, replace the two `_extract_source(...)` calls with `extract_symbol_source(...)`:

```python
        old_code = extract_symbol_source(fc.old_content if fc else None, file, qualified_name)
        new_code = extract_symbol_source(fc.new_content if fc else None, file, qualified_name)
```

- [ ] **Step 5: Run tests to verify green (new + unchanged investigator behavior)**

Run: `python3 -m pytest tests/unit/test_source.py tests/unit/test_investigator.py -v`
Expected: PASS — the new source tests pass and every existing investigator test still passes (behavior-preserving move).

- [ ] **Step 6: Commit**

```bash
git add src/detection/source.py src/detection/investigator.py tests/unit/test_source.py
git commit -m "refactor: promote symbol-source extractor to shared helper"
```

---

## Task 2: Repair data models

**Files:**
- Modify: `src/detection/models.py`
- Test: `tests/unit/test_repair_models.py`

**Interfaces:**
- Consumes: `ChangeKind` (already in `models.py`).
- Produces (all in `src/detection/models.py`):
  - `RepairInput` (frozen): `symbol_id: str`, `section_id: str`, `file: str`, `change_kind: ChangeKind`, `symbol_name: str`, `new_code: str | None`, `section_text: str`, `reason: str`, `wrong_claims: tuple[str, ...]`, `verdict_confidence: float`.
  - `RepairProposal` (frozen): `symbol_id: str`, `section_id: str`, `file: str`, `original_text: str`, `revised_text: str`, `diff: str`, `changed: bool`.
  - `ValidationResult` (frozen): `accurate: bool`, `preserved: bool`, `style_ok: bool`, `notes: str`.
  - `RepairRoute` (`enum.Enum`): `AUTOFIX = "autofix"`, `FLAG = "flag"`, `NO_CHANGE = "no_change"`.
  - `RepairOutcome` (frozen): `proposal: RepairProposal`, `validation: ValidationResult | None`, `route: RepairRoute`, `reason: str`.
  - `RepairResult` (mutable dataclass): `outcomes: list[RepairOutcome] = field(default_factory=list)`, `skipped: dict[str, int] = field(default_factory=dict)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_repair_models.py`:

```python
from src.detection.models import (
    ChangeKind,
    RepairInput,
    RepairOutcome,
    RepairProposal,
    RepairResult,
    RepairRoute,
    ValidationResult,
)


def test_repair_input_is_frozen_and_holds_fields():
    inp = RepairInput(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        file="app.py",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        symbol_name="create_user",
        new_code="def create_user(name, email): ...",
        section_text="Use create_user to make a user.",
        reason="signature changed",
        wrong_claims=("create_user(name)",),
        verdict_confidence=0.9,
    )
    assert inp.change_kind is ChangeKind.SIGNATURE_CHANGED
    assert inp.verdict_confidence == 0.9


def test_repair_route_values():
    assert RepairRoute.AUTOFIX.value == "autofix"
    assert RepairRoute.FLAG.value == "flag"
    assert RepairRoute.NO_CHANGE.value == "no_change"


def test_repair_outcome_and_result_defaults():
    proposal = RepairProposal(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        file="README.md",
        original_text="old",
        revised_text="new",
        diff="--- a\n+++ b\n-old\n+new",
        changed=True,
    )
    validation = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")
    outcome = RepairOutcome(
        proposal=proposal, validation=validation, route=RepairRoute.AUTOFIX, reason="ok"
    )
    result = RepairResult()
    result.outcomes.append(outcome)
    result.skipped["repair_error"] = 1
    assert result.outcomes[0].route is RepairRoute.AUTOFIX
    assert result.outcomes[0].validation.accurate is True
    assert result.skipped == {"repair_error": 1}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_repair_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'RepairInput'`.

- [ ] **Step 3: Add the models**

In `src/detection/models.py`, confirm `import enum` and `from dataclasses import dataclass, field` are present at the top (they are — existing models use them). Append at the end of the file:

```python
@dataclass(frozen=True)
class RepairInput:
    """Evidence bundle for repairing one stale doc section.

    Attributes:
        symbol_id: ``ChangedSymbol.id`` of the symbol whose change made the section stale.
        section_id: Identifier of the documentation section to repair.
        file: Repo-relative path of the doc file containing the section.
        change_kind: The kind of change made to the underlying symbol.
        symbol_name: Unqualified name of the symbol.
        new_code: The symbol's source after the change, or None if it no longer exists.
        section_text: Full current text of the documentation section.
        reason: The investigator's explanation for why the section is stale.
        wrong_claims: Specific claims in the section that are no longer accurate.
        verdict_confidence: The investigator's staleness confidence, from 0.0 to 1.0.
    """

    symbol_id: str
    section_id: str
    file: str
    change_kind: ChangeKind
    symbol_name: str
    new_code: str | None
    section_text: str
    reason: str
    wrong_claims: tuple[str, ...]
    verdict_confidence: float


@dataclass(frozen=True)
class RepairProposal:
    """A proposed rewrite of a stale doc section.

    Attributes:
        symbol_id: ``ChangedSymbol.id`` of the implicated symbol.
        section_id: Identifier of the documentation section.
        file: Repo-relative path of the doc file.
        original_text: The section text before repair.
        revised_text: The LLM's rewritten section text.
        diff: Unified diff of original vs. revised, or "" when nothing changed.
        changed: Whether the rewrite differs from the original (ignoring surrounding
            whitespace).
    """

    symbol_id: str
    section_id: str
    file: str
    original_text: str
    revised_text: str
    diff: str
    changed: bool


@dataclass(frozen=True)
class ValidationResult:
    """An independent quality judgment of a repair proposal.

    Attributes:
        accurate: Whether the revised text correctly describes the new code.
        preserved: Whether already-correct parts were left intact.
        style_ok: Whether tone/structure/formatting is consistent with the original.
        notes: Short free-text explanation from the validator.
    """

    accurate: bool
    preserved: bool
    style_ok: bool
    notes: str


class RepairRoute(enum.Enum):
    """Where a repair proposal is routed by the confidence router.

    Attributes:
        AUTOFIX: High-confidence, mechanical, validator-clean — eligible for a fix-PR.
        FLAG: Needs human review (validator flag, risky change kind, or low confidence).
        NO_CHANGE: The rewrite changed nothing; nothing to route.
    """

    AUTOFIX = "autofix"
    FLAG = "flag"
    NO_CHANGE = "no_change"


@dataclass(frozen=True)
class RepairOutcome:
    """The routed result of repairing one stale section.

    Attributes:
        proposal: The proposed rewrite and its diff.
        validation: The validator's judgment, or None when the route is NO_CHANGE.
        route: The routing decision.
        reason: Human-readable explanation for the route.
    """

    proposal: RepairProposal
    validation: ValidationResult | None
    route: RepairRoute
    reason: str


@dataclass
class RepairResult:
    """The full output of a repair run over a diff.

    Attributes:
        outcomes: One RepairOutcome per stale section that was processed.
        skipped: Counts of sections excluded, keyed by reason (e.g. ``"repair_error"``,
            ``"validation_error"``).
    """

    outcomes: list[RepairOutcome] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_repair_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/detection/models.py tests/unit/test_repair_models.py
git commit -m "feat: add repair engine data models"
```

---

## Task 3: Repair + validation prompts and schemas

**Files:**
- Modify: `src/llm/prompts.py`
- Test: `tests/unit/test_repair_prompts.py`

**Interfaces:**
- Consumes: `RepairInput`, `RepairProposal` (from `src/detection/models.py`).
- Produces (in `src/llm/prompts.py`):
  - `REPAIR_SYSTEM_PROMPT: str`, `build_repair_prompt(inp: RepairInput) -> str`, `REPAIR_SCHEMA: dict`.
  - `VALIDATE_SYSTEM_PROMPT: str`, `build_validate_prompt(inp: RepairInput, proposal: RepairProposal) -> str`, `VALIDATION_SCHEMA: dict`.
- The repair-prompt output MUST contain the literal word `Rewrite`; the validate-prompt output MUST contain the literal phrase `proposed revision` (anchors for the integration fake).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_repair_prompts.py`:

```python
from src.detection.models import ChangeKind, RepairInput, RepairProposal
from src.llm.prompts import (
    REPAIR_SCHEMA,
    VALIDATION_SCHEMA,
    build_repair_prompt,
    build_validate_prompt,
)

INP = RepairInput(
    symbol_id="app.py::create_user",
    section_id="README.md#users",
    file="README.md",
    change_kind=ChangeKind.SIGNATURE_CHANGED,
    symbol_name="create_user",
    new_code="def create_user(name, email):\n    ...",
    section_text="Use `create_user(name)` to make a user.",
    reason="create_user now takes an email argument",
    wrong_claims=("create_user(name)",),
    verdict_confidence=0.9,
)


def test_repair_prompt_contains_evidence_and_anchor():
    p = build_repair_prompt(INP)
    assert "Rewrite" in p                       # anchor for the integration fake
    assert "create_user(name, email)" in p      # new code
    assert "Use `create_user(name)` to make a user." in p  # section text
    assert "create_user now takes an email argument" in p  # reason
    assert "create_user(name)" in p             # wrong claim


def test_validate_prompt_contains_both_texts_and_anchor():
    proposal = RepairProposal(
        symbol_id=INP.symbol_id,
        section_id=INP.section_id,
        file=INP.file,
        original_text=INP.section_text,
        revised_text="Use `create_user(name, email)` to make a user.",
        diff="",
        changed=True,
    )
    p = build_validate_prompt(INP, proposal)
    assert "proposed revision" in p             # anchor for the integration fake
    assert "Use `create_user(name)` to make a user." in p        # original
    assert "Use `create_user(name, email)` to make a user." in p  # revised
    assert "def create_user(name, email):" in p                   # new code


def test_schema_shapes():
    assert REPAIR_SCHEMA["required"] == ["revised_text"]
    assert REPAIR_SCHEMA["additionalProperties"] is False
    assert set(VALIDATION_SCHEMA["required"]) == {"accurate", "preserved", "style_ok", "notes"}
    assert VALIDATION_SCHEMA["additionalProperties"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_repair_prompts.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_repair_prompt'`.

- [ ] **Step 3: Add the prompts and schemas**

In `src/llm/prompts.py`, update the import line to also bring in the new types:

```python
from src.detection.models import InvestigationInput, RepairInput, RepairProposal
```

Then append at the end of the file:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_repair_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm/prompts.py tests/unit/test_repair_prompts.py
git commit -m "feat: repair and validation prompts and schemas"
```

---

## Task 4: Repair Engine (`repair_section`)

**Files:**
- Modify (replace stub): `src/repair/repairer.py`
- Test: `tests/unit/test_repairer.py`

**Interfaces:**
- Consumes: `LLMClient` (`src/llm/client.py`), `RepairInput`/`RepairProposal` (models), `REPAIR_SYSTEM_PROMPT`/`build_repair_prompt`/`REPAIR_SCHEMA` (prompts).
- Produces: `repair_section(inp: RepairInput, client: LLMClient) -> RepairProposal`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_repairer.py`:

```python
import pytest

from src.detection.models import ChangeKind, RepairInput
from src.llm.client import FakeLLMClient
from src.repair.repairer import repair_section

INP = RepairInput(
    symbol_id="app.py::create_user",
    section_id="README.md#users",
    file="README.md",
    change_kind=ChangeKind.SIGNATURE_CHANGED,
    symbol_name="create_user",
    new_code="def create_user(name, email):\n    ...",
    section_text="Use `create_user(name)` to make a user.",
    reason="now takes email",
    wrong_claims=("create_user(name)",),
    verdict_confidence=0.9,
)


def test_repair_produces_diff_when_changed():
    client = FakeLLMClient({"revised_text": "Use `create_user(name, email)` to make a user."})
    proposal = repair_section(INP, client)
    assert proposal.changed is True
    assert proposal.section_id == "README.md#users"
    assert proposal.original_text == INP.section_text
    assert proposal.revised_text == "Use `create_user(name, email)` to make a user."
    assert "-Use `create_user(name)` to make a user." in proposal.diff
    assert "+Use `create_user(name, email)` to make a user." in proposal.diff


def test_repair_no_op_when_identical():
    client = FakeLLMClient({"revised_text": INP.section_text})
    proposal = repair_section(INP, client)
    assert proposal.changed is False
    assert proposal.diff == ""


def test_repair_rejects_non_string_revised_text():
    client = FakeLLMClient({"revised_text": 123})
    with pytest.raises(ValueError):
        repair_section(INP, client)


def test_repair_rejects_missing_key():
    client = FakeLLMClient({"nope": "x"})
    with pytest.raises((ValueError, KeyError)):
        repair_section(INP, client)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_repairer.py -v`
Expected: FAIL — `repair_section` not importable (the stub has no such function).

- [ ] **Step 3: Implement `repair_section`**

Replace the entire contents of `src/repair/repairer.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_repairer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repair/repairer.py tests/unit/test_repairer.py
git commit -m "feat: repair engine rewrites stale sections with computed diff"
```

---

## Task 5: Validator (`validate_repair`)

**Files:**
- Modify (replace stub): `src/repair/validator.py`
- Test: `tests/unit/test_validator.py`

**Interfaces:**
- Consumes: `LLMClient`, `RepairInput`/`RepairProposal`/`ValidationResult` (models), `VALIDATE_SYSTEM_PROMPT`/`build_validate_prompt`/`VALIDATION_SCHEMA` (prompts).
- Produces: `validate_repair(inp: RepairInput, proposal: RepairProposal, client: LLMClient) -> ValidationResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_validator.py`:

```python
import pytest

from src.detection.models import ChangeKind, RepairInput, RepairProposal
from src.llm.client import FakeLLMClient
from src.repair.validator import validate_repair

INP = RepairInput(
    symbol_id="app.py::create_user",
    section_id="README.md#users",
    file="README.md",
    change_kind=ChangeKind.SIGNATURE_CHANGED,
    symbol_name="create_user",
    new_code="def create_user(name, email):\n    ...",
    section_text="Use `create_user(name)` to make a user.",
    reason="now takes email",
    wrong_claims=("create_user(name)",),
    verdict_confidence=0.9,
)
PROPOSAL = RepairProposal(
    symbol_id=INP.symbol_id,
    section_id=INP.section_id,
    file=INP.file,
    original_text=INP.section_text,
    revised_text="Use `create_user(name, email)` to make a user.",
    diff="(diff)",
    changed=True,
)


def test_validate_parses_all_flags():
    client = FakeLLMClient(
        {"accurate": True, "preserved": True, "style_ok": False, "notes": "tone drifted"}
    )
    result = validate_repair(INP, PROPOSAL, client)
    assert result.accurate is True
    assert result.preserved is True
    assert result.style_ok is False
    assert result.notes == "tone drifted"


def test_validate_rejects_non_boolean_flag():
    client = FakeLLMClient(
        {"accurate": "yes", "preserved": True, "style_ok": True, "notes": ""}
    )
    with pytest.raises(ValueError):
        validate_repair(INP, PROPOSAL, client)


def test_validate_rejects_missing_key():
    client = FakeLLMClient({"accurate": True, "preserved": True, "style_ok": True})
    with pytest.raises((ValueError, KeyError)):
        validate_repair(INP, PROPOSAL, client)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_validator.py -v`
Expected: FAIL — `validate_repair` not importable.

- [ ] **Step 3: Implement `validate_repair`**

Replace the entire contents of `src/repair/validator.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_validator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repair/validator.py tests/unit/test_validator.py
git commit -m "feat: independent validator gate for repair proposals"
```

---

## Task 6: Confidence Router (`route`)

**Files:**
- Modify (replace stub): `src/repair/confidence_router.py`
- Test: `tests/unit/test_confidence_router.py`

**Interfaces:**
- Consumes: `RepairProposal`/`ValidationResult`/`RepairRoute`/`ChangeKind` (models), `Settings` (`src/utils/config.py`).
- Produces: `route(proposal: RepairProposal, validation: ValidationResult | None, change_kind: ChangeKind, verdict_confidence: float, settings: Settings) -> tuple[RepairRoute, str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_confidence_router.py`:

```python
from src.detection.models import ChangeKind, RepairProposal, RepairRoute, ValidationResult
from src.repair.confidence_router import route
from src.utils.config import Settings

SETTINGS = Settings()  # defaults: threshold 0.8, autofix {signature_changed}
CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")


def _proposal(changed=True):
    return RepairProposal(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        file="README.md",
        original_text="old",
        revised_text="new" if changed else "old",
        diff="(d)" if changed else "",
        changed=changed,
    )


def test_no_change_when_proposal_unchanged():
    r, reason = route(_proposal(changed=False), None, ChangeKind.SIGNATURE_CHANGED, 0.99, SETTINGS)
    assert r is RepairRoute.NO_CHANGE


def test_autofix_when_clean_mechanical_and_confident():
    r, reason = route(_proposal(), CLEAN, ChangeKind.SIGNATURE_CHANGED, 0.9, SETTINGS)
    assert r is RepairRoute.AUTOFIX


def test_flag_when_validation_dirty():
    dirty = ValidationResult(accurate=True, preserved=False, style_ok=True, notes="dropped text")
    r, reason = route(_proposal(), dirty, ChangeKind.SIGNATURE_CHANGED, 0.9, SETTINGS)
    assert r is RepairRoute.FLAG
    assert "validation" in reason


def test_flag_when_change_kind_not_mechanical():
    for kind in (ChangeKind.ADDED, ChangeKind.REMOVED, ChangeKind.BODY_CHANGED):
        r, reason = route(_proposal(), CLEAN, kind, 0.9, SETTINGS)
        assert r is RepairRoute.FLAG


def test_flag_when_confidence_below_threshold():
    r, reason = route(_proposal(), CLEAN, ChangeKind.SIGNATURE_CHANGED, 0.5, SETTINGS)
    assert r is RepairRoute.FLAG
    assert "confidence" in reason


def test_autofix_set_is_config_driven():
    widened = Settings(repair_autofix_change_kinds=("signature_changed", "body_changed"))
    r, reason = route(_proposal(), CLEAN, ChangeKind.BODY_CHANGED, 0.9, widened)
    assert r is RepairRoute.AUTOFIX
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_confidence_router.py -v`
Expected: FAIL — `route` not importable.

- [ ] **Step 3: Implement `route`**

Replace the entire contents of `src/repair/confidence_router.py` with:

```python
"""Stage 8: route high-confidence -> fix-PR, low-confidence -> inline flag."""

from __future__ import annotations

from src.detection.models import ChangeKind, RepairProposal, RepairRoute, ValidationResult
from src.utils.config import Settings


def route(
    proposal: RepairProposal,
    validation: ValidationResult | None,
    change_kind: ChangeKind,
    verdict_confidence: float,
    settings: Settings,
) -> tuple[RepairRoute, str]:
    """Decide how to route a repair proposal, deterministically.

    A proposal is AUTOFIX only when it is a real change, the validator passed on all
    three axes, the change kind is configured as auto-fixable, and the investigator's
    staleness confidence meets the threshold. Everything else FLAGs for human review;
    a no-op rewrite is NO_CHANGE.

    Args:
        proposal: The proposed rewrite.
        validation: The validator's judgment, or None when the proposal did not change.
        change_kind: The kind of change made to the underlying symbol.
        verdict_confidence: The investigator's staleness confidence (0.0-1.0).
        settings: Repair routing configuration.

    Returns:
        A (RepairRoute, reason) tuple; ``reason`` explains the decision.
    """
    if not proposal.changed:
        return RepairRoute.NO_CHANGE, "rewrite made no change"

    clean = (
        validation is not None
        and validation.accurate
        and validation.preserved
        and validation.style_ok
    )
    mechanical = change_kind.value in settings.repair_autofix_change_kinds
    confident = verdict_confidence >= settings.repair_confidence_threshold

    if clean and mechanical and confident:
        return (
            RepairRoute.AUTOFIX,
            f"validated; {change_kind.value}; confidence {verdict_confidence:.2f}",
        )

    reasons: list[str] = []
    if not clean:
        reasons.append("validation flagged")
    if not mechanical:
        reasons.append(f"{change_kind.value} not auto-fixable")
    if not confident:
        reasons.append(
            f"confidence {verdict_confidence:.2f} < {settings.repair_confidence_threshold}"
        )
    return RepairRoute.FLAG, "; ".join(reasons)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_confidence_router.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repair/confidence_router.py tests/unit/test_confidence_router.py
git commit -m "feat: deterministic confidence router for repairs"
```

---

## Task 7: Repair input assembly (`build_repair_inputs`)

**Files:**
- Create: `src/repair/engine.py`
- Test: `tests/unit/test_repair_engine_inputs.py`

**Interfaces:**
- Consumes: `Verdict`/`Suspect`/`FileChange`/`RepairInput` (models), `Index` (`src/models.py`), `extract_symbol_source` (`src/detection/source.py`).
- Produces: `build_repair_inputs(verdicts: list[Verdict], suspects: list[Suspect], file_changes: list[FileChange], index: Index) -> list[RepairInput]`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_repair_engine_inputs.py`:

```python
from src.detection.models import ChangeKind, FileChange, Suspect, Verdict
from src.models import DocSection, Index
from src.repair.engine import build_repair_inputs

NEW_CODE = "def create_user(name, email):\n    return {}\n"


def _index():
    section = DocSection(
        id="README.md#users",
        heading_path=("Users",),
        file="README.md",
        raw="Use `create_user(name)` to make a user.",
        start_line=1,
        end_line=2,
        referenced_symbols=("create_user",),
        referenced_config_keys=(),
    )
    return Index(sections={"README.md#users": section})


def test_builds_input_joining_change_kind_and_new_code():
    verdict = Verdict(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        stale=True,
        confidence=0.9,
        reason="now takes email",
        wrong_claims=("create_user(name)",),
    )
    suspect = Suspect(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="index-link",
    )
    fc = FileChange(path="app.py", old_content=None, new_content=NEW_CODE, changed_lines=frozenset())
    inputs = build_repair_inputs([verdict], [suspect], [fc], _index())
    assert len(inputs) == 1
    inp = inputs[0]
    assert inp.change_kind is ChangeKind.SIGNATURE_CHANGED   # recovered via the join
    assert inp.symbol_name == "create_user"
    assert inp.section_text == "Use `create_user(name)` to make a user."
    assert inp.new_code is not None and "def create_user(name, email)" in inp.new_code
    assert inp.verdict_confidence == 0.9
    assert inp.wrong_claims == ("create_user(name)",)


def test_skips_verdict_without_matching_suspect_or_section():
    verdict = Verdict(
        symbol_id="app.py::ghost",
        section_id="README.md#missing",
        stale=True,
        confidence=0.9,
        reason="x",
        wrong_claims=(),
    )
    inputs = build_repair_inputs([verdict], [], [], _index())
    assert inputs == []
```

(Check the exact `Index` and `DocSection` constructor field names against `src/models.py` before running — mirror them exactly. If `Index` requires other fields, pass empty defaults as the existing index tests do.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_repair_engine_inputs.py -v`
Expected: FAIL — `src.repair.engine` does not exist.

- [ ] **Step 3: Implement `build_repair_inputs`**

Create `src/repair/engine.py`:

```python
"""Repair orchestration: assemble inputs and run repair->validate->route per section."""

from __future__ import annotations

import logging

from src.detection.models import (
    FileChange,
    RepairInput,
    Suspect,
    Verdict,
)
from src.detection.source import extract_symbol_source
from src.models import Index

logger = logging.getLogger(__name__)


def build_repair_inputs(
    verdicts: list[Verdict],
    suspects: list[Suspect],
    file_changes: list[FileChange],
    index: Index,
) -> list[RepairInput]:
    """Assemble per-verdict repair inputs from investigation + detection output.

    Joins each verdict to its suspect on ``(symbol_id, section_id)`` to recover the
    change kind, resolves the doc-section text from the index, and extracts the
    symbol's new source from the owning file change.

    Args:
        verdicts: Stale verdicts to repair (callers pass only ``stale`` verdicts).
        suspects: Detection suspects, used to recover each verdict's change kind.
        file_changes: The diffs the suspects were derived from.
        index: The current index, used to resolve doc section text.

    Returns:
        One RepairInput per unique ``(symbol_id, section_id)`` verdict whose suspect
        and section are both present. Verdicts without a matching suspect or section
        are skipped.
    """
    change_kind_by_key = {(s.symbol_id, s.section_id): s.change_kind for s in suspects}
    by_path = {fc.path: fc for fc in file_changes}
    seen: set[tuple[str, str]] = set()
    inputs: list[RepairInput] = []

    for verdict in verdicts:
        key = (verdict.symbol_id, verdict.section_id)
        if key in seen:
            continue

        change_kind = change_kind_by_key.get(key)
        section = index.sections.get(verdict.section_id)
        if change_kind is None or section is None:
            continue
        seen.add(key)

        file, qualified_name = verdict.symbol_id.split("::", 1)
        symbol_name = qualified_name.rsplit(".", 1)[-1]
        fc = by_path.get(file)
        new_code = extract_symbol_source(fc.new_content if fc else None, file, qualified_name)

        inputs.append(
            RepairInput(
                symbol_id=verdict.symbol_id,
                section_id=verdict.section_id,
                file=section.file,
                change_kind=change_kind,
                symbol_name=symbol_name,
                new_code=new_code,
                section_text=section.raw,
                reason=verdict.reason,
                wrong_claims=verdict.wrong_claims,
                verdict_confidence=verdict.confidence,
            )
        )

    return inputs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_repair_engine_inputs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repair/engine.py tests/unit/test_repair_engine_inputs.py
git commit -m "feat: assemble repair inputs from verdicts and detection output"
```

---

## Task 8: Orchestrator (`repair_pr`)

**Files:**
- Modify: `src/repair/engine.py`
- Test: `tests/integration/test_repair_pr.py`

**Interfaces:**
- Consumes: `run_detection` (`src/detection/detector.py`), `build_investigation_inputs`/`investigate` (`src/detection/investigator.py`), `load_index` (`src/index/store.py`), `Settings`, `LLMClient`, `repair_section`/`validate_repair`/`route` (repair modules), `build_repair_inputs` (Task 7).
- Produces: `repair_pr(repo_root: str, base: str, head: str, index_path: str, settings: Settings, client: LLMClient) -> RepairResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_repair_pr.py`. This mirrors the temp-git-repo + index fixture pattern used by `tests/integration/test_cli_investigate.py` — **read that file first** and reuse the same helper style (`git init`, base commit, head commit, `build_index(..., embeddings=False)`).

```python
import subprocess
from pathlib import Path

from src.detection.models import RepairRoute
from src.index.builder import build_index
from src.llm.client import FakeLLMClient
from src.repair.engine import repair_pr
from src.utils.config import Settings

APP_BASE = "def create_user(name):\n    return {'name': name}\n"
APP_HEAD = "def create_user(name, email):\n    return {'name': name, 'email': email}\n"
README = (
    "# Sample\n\n## Users\n\nUse `create_user(name)` to make a user.\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def _fake_pipeline_client() -> FakeLLMClient:
    corrected = "Use `create_user(name, email)` to make a user."

    def respond(user: str) -> dict:
        if "Rewrite" in user:  # repair call
            return {"revised_text": corrected}
        if "proposed revision" in user:  # validate call
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        # staleness verdict call
        return {
            "stale": True,
            "confidence": 0.9,
            "reason": "create_user now takes an email argument",
            "wrong_claims": ["create_user(name)"],
        }

    return FakeLLMClient(respond)


def _setup_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text(APP_BASE)
    (repo / "README.md").write_text(README)
    base = _commit_all(repo, "base")
    (repo / "app.py").write_text(APP_HEAD)
    head = _commit_all(repo, "head")
    index_path = str(repo / ".docsmith" / "index.json")
    build_index(str(repo), output_path=index_path, embeddings=False, full=True)
    return repo, base, head, index_path


def test_repair_pr_autofixes_signature_change(tmp_path):
    repo, base, head, index_path = _setup_repo(tmp_path)
    result = repair_pr(str(repo), base, head, index_path, Settings(), _fake_pipeline_client())
    autofixes = [o for o in result.outcomes if o.route is RepairRoute.AUTOFIX]
    assert len(autofixes) == 1
    outcome = autofixes[0]
    assert outcome.proposal.section_id == "README.md#users"
    assert "create_user(name, email)" in outcome.proposal.revised_text
    assert "+Use `create_user(name, email)` to make a user." in outcome.proposal.diff
    assert outcome.validation is not None and outcome.validation.accurate is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_repair_pr.py -v`
Expected: FAIL — `repair_pr` not importable from `src.repair.engine`.

- [ ] **Step 3: Implement `repair_pr`**

Append to `src/repair/engine.py`. First extend the imports at the top of the file. Replace the existing `from src.detection.models import (...)` block (added in Task 7) with the expanded one below, and add the new stage/orchestration imports:

```python
from src.detection.detector import run_detection
from src.detection.investigator import build_investigation_inputs, investigate
from src.detection.models import (
    FileChange,
    RepairInput,
    RepairOutcome,
    RepairResult,
    Suspect,
    Verdict,
)
from src.index.store import load_index
from src.llm.client import LLMClient
from src.repair.confidence_router import route
from src.repair.repairer import repair_section
from src.repair.validator import validate_repair
from src.utils.config import Settings
```

(The pre-existing `from src.detection.source import extract_symbol_source` and `from src.models import Index` lines from Task 7 stay.)

Then append the function:

```python
def repair_pr(
    repo_root: str,
    base: str,
    head: str,
    index_path: str,
    settings: Settings,
    client: LLMClient,
) -> RepairResult:
    """Run detection, investigation, and repair end-to-end for a base/head diff.

    Re-composes the detection and investigation stages directly (rather than calling
    ``investigate_pr``, whose return value discards the suspects and file changes that
    repair-input assembly needs), keeps only the stale verdicts, then for each one
    rewrites the section, validates the rewrite (when it changed), and routes it.

    Args:
        repo_root: Path to the git working tree.
        base: Base ref (old revision).
        head: Head ref (new revision).
        index_path: Filesystem path to the persisted index JSON.
        settings: Configuration for detection and repair routing.
        client: The LLM client used for both the investigation and repair calls.

    Returns:
        A RepairResult with one RepairOutcome per processed stale section, plus skip
        counts for sections whose repair or validation reply was malformed.

    Raises:
        RuntimeError: If the backend is unavailable (propagated from the LLM client).
    """
    detection, file_changes = run_detection(repo_root, base, head, index_path, settings)
    index = load_index(index_path)

    inv_inputs = build_investigation_inputs(detection.suspects, file_changes, index)
    inv_result = investigate(inv_inputs, client)
    stale = [v for v in inv_result.verdicts if v.stale]

    repair_inputs = build_repair_inputs(stale, detection.suspects, file_changes, index)

    result = RepairResult()
    for inp in repair_inputs:
        try:
            proposal = repair_section(inp, client)
        except (ValueError, KeyError, TypeError) as exc:  # noqa: PERF203
            result.skipped["repair_error"] = result.skipped.get("repair_error", 0) + 1
            logger.warning("Skipping repair for section=%s: %s", inp.section_id, exc)
            continue

        validation = None
        if proposal.changed:
            try:
                validation = validate_repair(inp, proposal, client)
            except (ValueError, KeyError, TypeError) as exc:
                result.skipped["validation_error"] = (
                    result.skipped.get("validation_error", 0) + 1
                )
                logger.warning("Skipping validation for section=%s: %s", inp.section_id, exc)
                continue

        route_result, reason = route(
            proposal, validation, inp.change_kind, inp.verdict_confidence, settings
        )
        result.outcomes.append(
            RepairOutcome(
                proposal=proposal, validation=validation, route=route_result, reason=reason
            )
        )

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/integration/test_repair_pr.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite + ruff**

Run: `python3 -m pytest -q && python3 -m ruff check src/repair docsmith.py`
Expected: all green; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/repair/engine.py tests/integration/test_repair_pr.py
git commit -m "feat: repair_pr orchestrates detect->investigate->repair->route"
```

---

## Task 9: `docsmith repair` CLI

**Files:**
- Modify: `docsmith.py`
- Test: `tests/integration/test_cli_repair.py`

**Interfaces:**
- Consumes: `repair_pr`/`make_client` (`src/repair/engine.py` and `src/detection/investigator.py`), `RepairRoute` (models), `load_settings`.
- Produces: the `repair` subcommand.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_cli_repair.py`. Reuse the temp-repo helpers from `tests/integration/test_repair_pr.py` (copy the `_git`/`_commit_all`/`_setup_repo` helpers, or import them). The CLI is driven with `--backend fake`; the fake backend must yield the same three-call pipeline. Because the CLI builds its own client via `make_client`, this test asserts on the *unit-level* behavior by monkeypatching `docsmith.make_client` to return the pipeline fake, then invoking `docsmith.main()`:

```python
import sys

import docsmith
from src.detection.models import RepairRoute  # noqa: F401  (ensures import path is valid)
from tests.integration.test_repair_pr import _fake_pipeline_client, _setup_repo


def test_cli_repair_prints_autofix_and_diff(tmp_path, monkeypatch, capsys):
    repo, base, head, index_path = _setup_repo(tmp_path)
    monkeypatch.setattr(docsmith, "make_client", lambda settings, backend_override=None: _fake_pipeline_client())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docsmith", "repair",
            "--repo", str(repo),
            "--base", base,
            "--head", head,
            "--index", index_path,
            "--backend", "fake",
        ],
    )
    docsmith.main()
    out = capsys.readouterr().out
    assert "AUTOFIX" in out
    assert "README.md#users" in out
    assert "create_user(name, email)" in out
    assert "auto-fixable" in out  # rollup line


def test_cli_repair_backend_unavailable_exits_1(tmp_path, monkeypatch, capsys):
    repo, base, head, index_path = _setup_repo(tmp_path)

    def boom(repo_root, base, head, index_path, settings, client):
        raise RuntimeError("Could not reach Ollama at http://localhost:11434 — run `ollama pull ...`")

    monkeypatch.setattr(docsmith, "make_client", lambda settings, backend_override=None: object())
    monkeypatch.setattr(docsmith, "repair_pr", boom)
    monkeypatch.setattr(
        sys, "argv",
        ["docsmith", "repair", "--repo", str(repo), "--base", base, "--head", head,
         "--index", index_path, "--backend", "ollama"],
    )
    try:
        docsmith.main()
        raised = False
    except SystemExit as exc:
        raised = True
        assert exc.code == 1
    assert raised
    err = capsys.readouterr().err
    assert "Ollama" in err
```

(If importing helpers from another test module is awkward in this project's layout, copy the `_git`/`_commit_all`/`_setup_repo`/`_fake_pipeline_client` helpers into this file verbatim instead.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_cli_repair.py -v`
Expected: FAIL — no `repair` subcommand (argparse error / `SystemExit 2`).

- [ ] **Step 3: Add the subparser**

In `docsmith.py`, extend the imports:

```python
from src.detection.investigator import investigate_pr, make_client
from src.detection.models import RepairRoute
from src.repair.engine import repair_pr
```

After the `investigate_parser` block (before `args = parser.parse_args()`), add a `repair` subparser mirroring `investigate` and adding `--threshold`:

```python
    repair_parser = subparsers.add_parser(
        "repair",
        help="Propose doc corrections for stale sections and route them by confidence.",
    )
    repair_parser.add_argument("--repo", default=".", help="Repository root (default: cwd).")
    repair_parser.add_argument("--base", required=True, help="Base git ref (old revision).")
    repair_parser.add_argument("--head", required=True, help="Head git ref (new revision).")
    repair_parser.add_argument(
        "--index",
        default=".docsmith/index.json",
        help="Path to the persisted index JSON (default: .docsmith/index.json).",
    )
    repair_parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="Path to the layered YAML config (default: configs/base.yaml).",
    )
    repair_parser.add_argument(
        "--backend",
        choices=["fake", "ollama", "claude"],
        default=None,
        help="LLM backend to use (default: from config).",
    )
    repair_parser.add_argument(
        "--model", default=None, help="Model override for the selected backend."
    )
    repair_parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the AUTOFIX confidence threshold (default: from config).",
    )
```

- [ ] **Step 4: Add the `repair` branch**

After the `elif args.subcommand == "investigate":` block, add:

```python
    elif args.subcommand == "repair":
        settings = load_settings(args.config)

        if args.model:
            effective_backend = args.backend or settings.llm_backend
            if effective_backend == "claude":
                settings.claude_model = args.model
            else:
                settings.ollama_model = args.model
        if args.threshold is not None:
            settings.repair_confidence_threshold = args.threshold

        client = make_client(settings, backend_override=args.backend)
        try:
            result = repair_pr(args.repo, args.base, args.head, args.index, settings, client)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        n_auto = n_flag = n_nochange = 0
        for outcome in result.outcomes:
            proposal = outcome.proposal
            symbol_name = proposal.symbol_id.split("::")[-1].rsplit(".", 1)[-1]
            if outcome.route is RepairRoute.NO_CHANGE:
                n_nochange += 1
                continue
            label = "AUTOFIX " if outcome.route is RepairRoute.AUTOFIX else "FLAG    "
            if outcome.route is RepairRoute.AUTOFIX:
                n_auto += 1
            else:
                n_flag += 1
            print(f"{label} {proposal.section_id} — {symbol_name}   ({outcome.reason})")
            for line in proposal.diff.splitlines():
                print(f"  {line}")

        n_skipped = sum(result.skipped.values())
        print(
            f"{n_auto} auto-fixable · {n_flag} flagged · "
            f"{n_nochange} unchanged · {n_skipped} skipped"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/integration/test_cli_repair.py -v`
Expected: PASS (both tests).

- [ ] **Step 6: Full suite + ruff**

Run: `python3 -m pytest -q && python3 -m ruff check docsmith.py src/repair`
Expected: green; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add docsmith.py tests/integration/test_cli_repair.py
git commit -m "feat: docsmith repair CLI subcommand"
```

---

## Task 10: Free demo + gated real-Ollama repair test

**Files:**
- Modify: `Makefile`
- Create: `scripts/dev/repair_demo.sh`
- Modify: `README.md`
- Create: `tests/integration/test_repair_ollama.py`

**Interfaces:**
- Consumes: the `docsmith repair` CLI and `repair_pr` (`src/repair/engine.py`) + `make_client`.

- [ ] **Step 1: Write the gated test (collectable, skips cleanly)**

Read the existing `tests/integration/test_investigate_ollama.py` and mirror its skip-guard exactly. Create `tests/integration/test_repair_ollama.py`:

```python
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

from src.detection.models import RepairRoute
from src.index.builder import build_index
from src.repair.engine import make_client, repair_pr  # make_client re-exported below
from src.utils.config import load_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_OLLAMA_TESTS") != "1",
    reason="set DOCSMITH_RUN_OLLAMA_TESTS=1 to run the real-Ollama repair test",
)

APP_BASE = "def create_user(name):\n    return {'name': name}\n"
APP_HEAD = "def create_user(name, email):\n    return {'name': name, 'email': email}\n"
README = "# Sample\n\n## Users\n\nUse `create_user(name)` to make a user.\n"


def _ollama_reachable(host: str) -> bool:
    parsed = urlparse(host)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 11434), timeout=1):
            return True
    except OSError:
        return False


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def test_real_ollama_repairs_signature_change(tmp_path):
    settings = load_settings("configs/base.yaml")
    if not _ollama_reachable(settings.ollama_host):
        pytest.skip("Ollama not reachable")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "app.py").write_text(APP_BASE)
    (repo / "README.md").write_text(README)
    base = _commit(repo, "base")
    (repo / "app.py").write_text(APP_HEAD)
    head = _commit(repo, "head")
    index_path = str(repo / ".docsmith" / "index.json")
    build_index(str(repo), output_path=index_path, embeddings=False, full=True)

    client = make_client(settings, backend_override="ollama")
    result = repair_pr(str(repo), base, head, index_path, settings, client)

    changed = [o for o in result.outcomes if o.proposal.changed]
    assert changed, "expected at least one changed repair proposal"
    assert any("email" in o.proposal.revised_text for o in changed)
    assert all(o.route in RepairRoute for o in result.outcomes)
```

> `make_client` currently lives in `src/detection/investigator.py`. To let repair code and this test import it from `src.repair.engine`, add a re-export in `src/repair/engine.py`: `from src.detection.investigator import build_investigation_inputs, investigate, make_client` and include `make_client` in that import (it's already imported for `investigate`). If it's cleaner, import `make_client` directly from `src.detection.investigator` in the test instead — either is fine; pick one and keep it consistent.

- [ ] **Step 2: Run to verify it SKIPS cleanly (not errors)**

Run: `python3 -m pytest tests/integration/test_repair_ollama.py -rs -v`
Expected: `1 skipped` with the reason shown; **no collection error**.

- [ ] **Step 3: Add the demo script**

Create `scripts/dev/repair_demo.sh` (mirror `scripts/dev/investigate_demo.sh`; make it executable with `chmod +x`):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Free, local, end-to-end Docsmith repair demo — no API key, $0.
# Requires Ollama running with the model pulled: `ollama pull qwen2.5-coder:7b`.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp -R "$REPO_ROOT/tests/fixtures/sample_repo/." "$WORK/"
cd "$WORK"
git init -q
git config user.email "demo@example.com"
git config user.name "Docsmith Demo"
git add -A
git commit -q -m "base"
BASE="$(git rev-parse HEAD)"

python "$REPO_ROOT/docsmith.py" build-index --repo "$WORK" \
  --output "$WORK/.docsmith/index.json" --no-embeddings

# Scripted signature change to a documented function.
python - "$WORK/app.py" <<'PY'
import sys
path = sys.argv[1]
text = open(path).read()
text = text.replace(
    "def create_user(name: str, email: str) -> dict:",
    'def create_user(name: str, email: str, role: str = "member") -> dict:',
)
open(path, "w").write(text)
PY

git add -A
git commit -q -m "change create_user signature"
HEAD="$(git rev-parse HEAD)"

echo "Running Docsmith repair on a local Ollama model — \$0, no API key…"
python "$REPO_ROOT/docsmith.py" repair --repo "$WORK" --base "$BASE" --head "$HEAD" \
  --index "$WORK/.docsmith/index.json" --config "$REPO_ROOT/configs/base.yaml" \
  --backend ollama
```

- [ ] **Step 4: Add the Make target**

In `Makefile`, add `repair-demo` to `.PHONY` and add the target (mirror `investigate-demo`):

```makefile
.PHONY: repair-demo
repair-demo:
	bash scripts/dev/repair_demo.sh
```

- [ ] **Step 5: Verify script syntax**

Run: `bash -n scripts/dev/repair_demo.sh`
Expected: no output (syntactically valid).

- [ ] **Step 6: README section**

In `README.md`, add a short subsection near the existing investigate demo, e.g. after the "See it work (free, local)" section:

```markdown
### See it fix docs (free, local)

With Ollama running (`ollama pull qwen2.5-coder:7b`), propose real doc corrections
on the bundled fixture — no API key, $0:

```bash
make repair-demo
```

Docsmith rewrites the stale section, an independent LLM pass validates the rewrite,
and each fix is routed: **AUTOFIX** (clean, mechanical, high-confidence) or **FLAG**
(needs human review). It prints the proposed unified diff; it never writes files or
opens PRs (that's the Week 5 GitHub Action). The backend is pluggable — `fake`
(offline tests), `ollama` (default), or `claude` (optional, needs `ANTHROPIC_API_KEY`).
```

- [ ] **Step 7: Full suite (gated test skipped) + ruff**

Run: `python3 -m pytest -q -rs && python3 -m ruff check .`
Expected: all pass with the real-Ollama repair test SKIPPED; ruff clean.

- [ ] **Step 8: Commit**

```bash
git add Makefile scripts/dev/repair_demo.sh README.md tests/integration/test_repair_ollama.py
git commit -m "feat: free local repair demo and gated ollama test"
```

---

## Definition of Done (from the spec)

- `docsmith repair --backend ollama` produces routed corrections (AUTOFIX / FLAG / NO_CHANGE) with unified diffs for a real git range on a local model, at $0.
- Repair Engine + Validator + Confidence Router implemented behind the reused `LLMClient` seam; importing modules needs no SDK/key/network.
- Whole-section rewrite + deterministic diff; malformed replies skipped, not fatal; backend-unavailable errors surfaced at the CLI (non-zero exit).
- `make repair-demo` runs the free end-to-end demo; README documents it.
- Default `pytest` suite fully offline ($0) and green; the gated real-Ollama repair test skips cleanly in CI; `ruff check .` clean.
- No LLM/AI attribution in any commit; living docs (roadmap/CHANGELOG) updated by the controller, not the task implementers.
