# Repair Engine (Week 4) — Design Spec

**Date:** 2026-08-13
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** LLM Staleness Investigator + Detection Core (Week 3) + Retrieval Core
(Week 2) + Index Core (Week 1)

---

## 1. Goal & Scope

Turn the investigator's **stale** `Verdict`s into **proposed doc corrections**. For each
confirmed-stale `(symbol, doc section)`, rewrite the section so it matches the new code,
run an independent LLM quality gate over the rewrite, and route the result to a confidence
tier (auto-fixable vs. needs-human-review). This is stages 6–8 of the original pipeline.

**In scope:**
- A **Repair Engine** (stage 6, LLM): whole-section rewrite that changes only what the
  verdict says is wrong, plus a deterministic unified diff of what changed.
- A **Validator** (stage 7, LLM): an independent second-opinion gate over each rewrite.
- A **Confidence Router** (stage 8, deterministic): AUTOFIX / FLAG / NO_CHANGE.
- Input assembly from investigation output + detection suspects + the index + git.
- A `docsmith repair` CLI and a **first-class, free demo path** (`make repair-demo`).
- Reuse of the `LLMClient` seam (`FakeLLMClient` / `OllamaClient` / `ClaudeClient`).

**Out of scope (Week 5 — GitHub Action):** creating branches, opening companion fix-PRs,
posting inline flags or summary comments, and any GitHub/network interaction. Week 4 is
**read-only**: it produces the corrections and routing decisions as data + diffs; Week 5
consumes them. No file writes either — a `--apply` local-write mode is a possible later
extension, deliberately deferred (YAGNI).

**Non-goals:** No repo/doc mutation. No auto-merge — a human always approves (Week 5). No
required paid API usage — the whole sub-project builds, tests, and demos at **$0**.

---

## 2. Cost posture (a hard requirement, carried over)

There is **no budget for paid API usage**. Identical posture to the investigator:

- **Tests** always use `FakeLLMClient` — no network, no key, **$0**, run in CI on every commit.
- **The demo** runs on `OllamaClient` → a local open-weights model — **$0**.
- **`ClaudeClient`** is optional, runs only if the user configures `ANTHROPIC_API_KEY`, and
  is never the default nor invoked by the default test suite.

Repair now costs **two LLM calls per stale section** (rewrite + validate); both are free on
local Ollama. Importing any module must never require the `anthropic` SDK, a network call,
or a key (lazy imports — the seam already guarantees this).

---

## 3. Architecture

Reuses the investigator's seam and orchestration shape; adds three focused components.

```
InvestigationResult.verdicts (stale only)  +  suspects  +  FileChanges  +  index
      │  build_repair_inputs
      │    · join verdict ↔ suspect on (symbol_id, section_id) → recover change_kind
      │    · doc-section text from index.sections[section_id].raw
      │    · new code re-parsed from the FileChange (same extraction as the investigator)
      ▼
[RepairInput(symbol_id, section_id, file, change_kind, symbol_name, new_code,
             section_text, reason, wrong_claims, verdict_confidence)]
      │
      ▼  Repair Engine (LLM #1) — repair_section
RepairProposal(original_text, revised_text, diff, changed)     ← difflib computes diff
      │
      ▼  Validator (LLM #2) — validate_repair   (skipped when changed is False)
ValidationResult(accurate, preserved, style_ok, notes)
      │
      ▼  Confidence Router (deterministic) — route
RepairOutcome(proposal, validation, route ∈ {AUTOFIX, FLAG, NO_CHANGE}, reason)
      ▼
RepairResult(outcomes, skipped)
```

`repair_pr(repo_root, base, head, index_path, settings, client) -> RepairResult` re-composes
the detection→investigation stages directly (rather than calling `investigate_pr`, whose
return value discards the `suspects` and `FileChange`s that `build_repair_inputs` needs):
`run_detection` → `build_investigation_inputs` → `investigate` → keep `stale` verdicts →
`build_repair_inputs(stale, result.suspects, file_changes, index)` → per input: repair →
validate → route. It reuses `make_client`, `run_detection`, `build_investigation_inputs`,
and `investigate` unchanged; the index is loaded once and shared across both assembly steps.

### 3.1 The `LLMClient` seam (reused, unchanged)
`complete_json(system, user, schema) -> dict`. Repair and validation are two independent
single-prompt structured calls — no agentic loop, consistent with the investigator.

---

## 4. Data models (`src/detection/models.py`, alongside `Verdict`)

- **`RepairProposal`** (frozen): `symbol_id: str`, `section_id: str`, `file: str`,
  `original_text: str`, `revised_text: str`, `diff: str` (unified diff, `""` when
  unchanged), `changed: bool`.
- **`ValidationResult`** (frozen): `accurate: bool`, `preserved: bool`, `style_ok: bool`,
  `notes: str`.
- **`RepairRoute`** (`Enum`): `AUTOFIX`, `FLAG`, `NO_CHANGE`.
- **`RepairOutcome`** (frozen): `proposal: RepairProposal`,
  `validation: ValidationResult | None` (None when `NO_CHANGE` — validation is skipped),
  `route: RepairRoute`, `reason: str` (human-readable routing explanation).
- **`RepairResult`** (mutable dataclass): `outcomes: list[RepairOutcome]`,
  `skipped: dict[str, int]` (e.g. `{"repair_error": 1, "validation_error": 0}`).

`RepairInput` (frozen) is an internal assembly type (may live in `src/repair/engine.py`):
`symbol_id`, `section_id`, `file`, `change_kind: ChangeKind`, `symbol_name: str`,
`new_code: str | None`, `section_text: str`, `reason: str`,
`wrong_claims: tuple[str, ...]`, `verdict_confidence: float`.

---

## 5. Components

### 5.1 Repair Engine (`src/repair/repairer.py`, stage 6)
- `repair_section(inp: RepairInput, client: LLMClient) -> RepairProposal`.
- Prompt (`build_repair_prompt`) supplies: the **full** current section text, the **new**
  code, and the diagnosis (`reason` + `wrong_claims`). The system prompt frames a precise
  technical editor who **changes only what the diagnosis says is wrong and preserves
  everything else verbatim** — tone, structure, formatting, correct prose. Output schema
  `REPAIR_SCHEMA = {revised_text: string}` (single required field, `additionalProperties:
  false`).
- The diff is computed **deterministically** with `difflib.unified_diff(original,
  revised)` — the "changed spans" the master spec asks for are a derived, trusted output,
  not something the LLM must localize. `changed = (revised_text.strip() !=
  original_text.strip())`; when unchanged, `diff = ""`.

### 5.2 Validator (`src/repair/validator.py`, stage 7)
- `validate_repair(inp: RepairInput, proposal: RepairProposal, client: LLMClient) ->
  ValidationResult`.
- An **independent** LLM call (fresh prompt via `build_validate_prompt`): given the
  original section, the revised section, the new code, and the diagnosis, judge three
  things. Output schema `VALIDATION_SCHEMA = {accurate: bool, preserved: bool, style_ok:
  bool, notes: string}` (all required, `additionalProperties: false`):
  - **accurate** — does the revised text correctly describe the new code?
  - **preserved** — were the parts that were already correct left intact (no unrelated
    rewrites, no dropped content)?
  - **style_ok** — is tone/structure/formatting consistent with the original?
- Only called when `proposal.changed` is `True` (a no-op rewrite needs no gate).

### 5.3 Confidence Router (`src/repair/confidence_router.py`, stage 8)
- `route(proposal, validation, change_kind, verdict_confidence, settings) -> tuple[
  RepairRoute, str]`. Pure and deterministic; biased toward FLAG (never auto-anything
  risky — a human always approves in Week 5).
  - **NO_CHANGE** — `proposal.changed is False`. The rewrite changed nothing; counted, not
    reported as a fix. `validation` is `None`.
  - **AUTOFIX** — *all* of: `validation.accurate and validation.preserved and
    validation.style_ok`; **and** `change_kind == ChangeKind.SIGNATURE_CHANGED` (renamed /
    re-typed parameters, changed defaults — the most mechanical, localized edits); **and**
    `verdict_confidence >= settings.repair_confidence_threshold` (default **0.8**).
  - **FLAG** — everything else: any validator flag false, or `change_kind ∈ {ADDED,
    REMOVED, BODY_CHANGED}` (new/removed capability or behavioral change — judgment-heavy),
    or staleness confidence below the threshold.
- The autofix-eligible change-kind set is **config-driven** (`repair.autofix_change_kinds`,
  default `["signature_changed"]`) so it can widen later without code changes. The `reason`
  string states which condition decided the route (for the CLI and Week-5 reporting).

### 5.4 Prompts & schemas (`src/llm/prompts.py`, extends the investigator's module)
Add `REPAIR_SYSTEM_PROMPT`, `build_repair_prompt(inp)`, `REPAIR_SCHEMA`,
`VALIDATE_SYSTEM_PROMPT`, `build_validate_prompt(inp, proposal)`, `VALIDATION_SCHEMA`.

### 5.5 Orchestrator (`src/repair/engine.py`)
`build_repair_inputs(verdicts, suspects, file_changes, index) -> list[RepairInput]` and
`repair_pr(...) -> RepairResult`. `build_repair_inputs` joins each stale `Verdict` to its
`Suspect` on `(symbol_id, section_id)` to recover `change_kind`, reads the section text from
`index.sections`, and extracts the symbol's new code from the owning `FileChange`. The
source-extraction helper from the investigator (`_extract_source`) is promoted to a shared
location (a small `src/detection/source.py`, imported by both the investigator and the repair
engine) and reused here rather than duplicated — closing the divergence the investigator's
final review flagged.

---

## 6. CLI + first-class free demo

- **`docsmith repair --repo . --base X --head Y [--index .docsmith/index.json]
  [--config configs/base.yaml] [--backend fake|ollama|claude] [--model ...]
  [--threshold 0.8]`** — runs detection → investigation → repair via the chosen backend
  (default from config = `ollama`), and prints, per stale section:
  ```
  AUTOFIX  README.md#users — create_user   (signature_changed, validated, conf 0.90)
    --- a/README.md
    +++ b/README.md
    @@ ... @@
    -Use `create_user(name)` to make a user.
    +Use `create_user(name, email)` to make a user.
  FLAG     README.md#formatting — formatName   (body_changed → needs review)
  ```
  followed by a rollup: `N auto-fixable · M flagged · K unchanged · J skipped`. Exit 0.
  Backend-unavailable errors surface a clear message and a **non-zero exit** (the §7 rule
  established for `investigate`). Read-only — no file writes, no git, no PRs.
- **Front-door demo (first-class):** a `make repair-demo` target + `scripts/dev/
  repair_demo.sh` (and a README "See it fix docs (free, local)" note): copies the fixture
  repo to a temp dir, builds the index, makes a scripted signature change to `create_user`,
  and runs `docsmith repair --backend ollama` end-to-end on the local model — printing the
  proposed README diff and the AUTOFIX route. **$0.**

---

## 7. Error handling

- A single section whose **repair** or **validation** LLM reply is missing/invalid JSON or
  fails schema validation is **skipped** (counted in `RepairResult.skipped["repair_error"]`
  or `["validation_error"]`), logged, and does not abort the batch.
- **Backend-unavailable** errors (`OllamaClient` can't reach Ollama; `ClaudeClient` missing
  key) are raised as a clear `RuntimeError` and **propagate** to the CLI boundary, which
  prints the actionable message and exits non-zero — never silently counted as skips. This
  matches the investigator's corrected behavior: validation/decode errors → skip;
  backend-unavailable → raise.

---

## 8. Config (`configs/base.yaml`, extends the existing `repair:` block)

```yaml
repair:
  confidence_threshold: 0.8              # min investigator staleness confidence for AUTOFIX
  autofix_change_kinds: [signature_changed]   # change kinds eligible for AUTOFIX
```

`load_settings` is extended to read these into `Settings` (with defaults
`repair_confidence_threshold = 0.8`, `repair_autofix_change_kinds =
("signature_changed",)`). Any existing unused keys in the block are left as-is.

---

## 9. Testing (default suite offline / $0)

- **Unit:**
  - `repair_section` with a `FakeLLMClient` scripted `revised_text` → asserts the diff is
    computed correctly and `changed` is set; a no-op rewrite (revised == original) →
    `changed is False`, `diff == ""`.
  - `validate_repair` with a scripted 3-flag reply → parses into `ValidationResult`; a
    malformed reply raises (caught upstream as a skip).
  - `route` **truth table**: SIGNATURE_CHANGED + all-clean + conf≥threshold → AUTOFIX;
    each validator flag false → FLAG; ADDED/REMOVED/BODY_CHANGED (even clean) → FLAG;
    conf<threshold → FLAG; `changed is False` → NO_CHANGE (validation None).
  - `build_repair_inputs`: a stale verdict + its suspect + `FileChange` + fixture index →
    correct `RepairInput` (change_kind recovered via the join, new code sliced by symbol,
    section text from the index, diagnosis carried through).
  - Prompt builders: `build_repair_prompt` / `build_validate_prompt` contain the section
    text, new code, and diagnosis (exact-substring assertions); schema shapes.
- **Integration (Fake backend):** full `repair_pr` on a temp git repo + built index with a
  `FakeLLMClient` scripted to (a) return a stale verdict for the changed symbol, then (b)
  return a corrected `revised_text`, then (c) return an all-clean validation → asserts one
  `AUTOFIX` outcome whose diff corrects the doc section, and that the CLI prints it. Runs in
  CI ($0). (The fake is driven by a callable keyed on prompt content to return the right
  payload for each of the three call types.)
- **Gated real-Ollama test (run locally):** the full `repair_pr` against a real local
  model, skipped unless `DOCSMITH_RUN_OLLAMA_TESTS=1` and Ollama is reachable — asserts a
  genuinely-stale signature change yields a `changed` rewrite that mentions the new
  parameter. Not run in CI.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM rewrites more than the stale part (drops or alters correct prose) | The Validator's `preserved` flag gates it; a false `preserved` forces FLAG, never AUTOFIX. The whole-section-rewrite + deterministic diff makes the blast radius visible in the printed diff. |
| Local model returns non-schema JSON | `format`=JSON-schema constrains output; per-section validation + skip keeps one bad reply from aborting the batch (same as the investigator). |
| Auto-fixing something subtle | AUTOFIX is deliberately narrow: only validator-clean, high-confidence `SIGNATURE_CHANGED` edits. Everything else FLAGs for human review. Config can widen the eligible set deliberately, never by accident. |
| Two LLM calls per section doubles cost/latency | Both are free on Ollama; validation is skipped entirely for NO_CHANGE sections; only `stale` verdicts reach repair at all (the investigator already filtered). |
| Source-extraction logic drifts from the investigator's | Promote the investigator's `_extract_source` to a shared helper and reuse it, rather than duplicating (removes a divergence class the final investigator review flagged). |

---

## 11. Definition of Done

- `docsmith repair --backend ollama` produces real, routed doc corrections (AUTOFIX / FLAG
  / NO_CHANGE) with unified diffs for a real git range on a local model, at **$0**.
- Repair Engine + Validator + Confidence Router implemented behind the reused `LLMClient`
  seam; importing modules needs no SDK/key/network.
- Whole-section rewrite with a deterministic diff; malformed replies skipped, not fatal;
  backend-unavailable errors surfaced at the CLI.
- `make repair-demo` runs the free end-to-end demo; README documents it.
- Default `pytest` suite is fully offline ($0) and green; `ruff check .` clean.
- The gated real-Ollama repair test exists and passes when run locally with Ollama.
