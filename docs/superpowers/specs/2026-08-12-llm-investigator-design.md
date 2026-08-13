# LLM Staleness Investigator — Design Spec

**Date:** 2026-08-12
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** Detection Core (Week 3) + Index Core (Week 1) + Retrieval Core (Week 2)

---

## 1. Goal & Scope

Turn the detector's **suspect** doc sections into **verdicts**. For each suspect
`(changed symbol, doc section)`, ask an LLM: *given how this code changed, is this doc
section actually stale — and if so, what specifically is wrong?* This is stage 5 of the
original pipeline and the project's first LLM integration.

**In scope:**
- An `LLMClient` seam with three backends: `FakeLLMClient` (tests), `OllamaClient` (local,
  free — the default), `ClaudeClient` (Anthropic SDK, optional/paid).
- A single-prompt **structured verdict** per suspect (no tools, no agentic loop).
- Prompt construction and `Verdict` parsing/validation.
- A `StalenessInvestigator` that assembles inputs from detection output + the index + git,
  and produces verdicts.
- An `investigate` CLI subcommand and a **first-class, free demo path**.

**Out of scope (own later sub-projects):** repair / rewrite / confidence-routing (Week 4);
the tool-equipped (read_file/grep) agentic investigator (a possible future enhancement);
the GitHub Action / PR reporting (Week 5).

**Non-goals:** No repo/doc mutation — the investigator only judges. No required paid API
usage — the whole sub-project builds, tests, and demos at **$0**.

---

## 2. Cost posture (a hard requirement)

There is **no budget for paid API usage**. The design guarantees:

- **Tests** always use `FakeLLMClient` — no network, no key, **$0**, run in CI on every commit.
- **The demo** runs on `OllamaClient` → a local open-weights model on the user's Mac — **$0**.
- **`ClaudeClient`** exists as an optional quality upgrade and runs **only** if the user
  configures an `ANTHROPIC_API_KEY`. It is never required, never the default, and never
  invoked by the default test suite.

Importing any module must never require the `anthropic` SDK, a network call, or a key
(lazy imports, mirroring `BgeSmallEmbedder`).

---

## 3. Architecture — the `LLMClient` seam

Mirrors the Week-2 `Embedder` seam: one protocol, a fake for tests, real backends behind it.

```
Suspect  +  index (doc-section text)  +  FileChange (old/new file content)
      │  build InvestigationInput(change_kind, symbol_name, old_code, new_code, doc_section_text, ids)
      ▼
StalenessInvestigator(llm_client)
      │  user+system prompt (prompts.py)  →  llm_client.complete_json(system, user, VERDICT_SCHEMA)
      ▼
Verdict(stale, confidence, reason, wrong_claims[])   →   InvestigationResult(verdicts, skipped)
```

### 3.1 `LLMClient` protocol (`src/llm/client.py`)
- Single method: `complete_json(system: str, user: str, schema: dict) -> dict` — returns a
  JSON object validated against `schema`. Provider-neutral and reusable by Week 4's repair
  engine.
- **`FakeLLMClient`** — constructed with a scripted response (or a callable mapping
  `user -> dict`); returns it verbatim. Deterministic, offline, no I/O. For tests.
- **`OllamaClient(model, host)`** — POSTs to the local Ollama HTTP API
  (`{host}/api/chat`, default `http://localhost:11434`) with the messages and a
  JSON-schema-constrained `format` so the model returns schema-valid JSON; parses and
  returns the object. Lazy (no import-time dependency); no key. **Default backend.**
- **`ClaudeClient(model)`** — Anthropic SDK, structured output via `output_config.format`
  (the `schema`), model `claude-sonnet-5`. Lazy-imports `anthropic` inside the method so
  importing the module never needs the SDK or a key. Optional/paid.

### 3.2 `StalenessInvestigator` (`src/detection/investigator.py` — the stage-5 stub)
- `investigate(inputs: list[InvestigationInput], client: LLMClient) -> InvestigationResult` —
  for each input, build the prompt (`prompts.py`), call `client.complete_json`, validate
  into a `Verdict`, attach the input's `symbol_id`/`section_id`. On a malformed/failed
  response for one input, record a skip in `InvestigationResult.skipped` (see §7) and
  continue — one bad verdict never aborts the batch. Returns the collected verdicts + skips.
- **Input assembly** (`build_investigation_inputs(suspects, file_changes, index) -> list[InvestigationInput]`):
  for each suspect, look up the doc section's `raw` text from `index.sections`, and extract
  the changed symbol's old/new source by **re-parsing** the owning `FileChange`'s
  `old_content`/`new_content` with `parse_source` and selecting the symbol by
  `qualified_name` (slicing its `start_line..end_line`). `old_code`/`new_code` are `None`
  when that side is absent (added/removed symbols). Dedups per `(symbol_id, section_id)`.

### 3.3 Orchestration (`src/detection/detector.py`, small refactor)
The investigator needs both the suspects **and** the `FileChange`s (for source). Refactor
so detection exposes both without a second git pass:
- Add `run_detection(repo_root, base, head, index_path, settings) -> tuple[DetectionResult, list[FileChange]]`.
- `detect(...)` becomes a thin wrapper returning just the `DetectionResult` (existing Week-3
  tests unchanged).
An `investigate_pr(repo_root, base, head, index_path, settings, client) -> InvestigationResult`
composes `run_detection` → `build_investigation_inputs` → `investigate`.

---

## 4. Data models (`src/detection/models.py`)

- **`Verdict`** (frozen): `symbol_id: str`, `section_id: str`, `stale: bool`,
  `confidence: float` (0–1), `reason: str`, `wrong_claims: tuple[str, ...]` (specific doc
  statements the change invalidated; empty when `stale is False`).
- **`InvestigationInput`** (frozen): `symbol_id: str`, `section_id: str`,
  `change_kind: ChangeKind`, `symbol_name: str`, `old_code: str | None`,
  `new_code: str | None`, `doc_section_text: str`.
- **`InvestigationResult`** (mutable dataclass): `verdicts: list[Verdict]`,
  `skipped: dict[str, int]` (reason → count, e.g. `{"llm_error": 1}`).

The JSON schema the LLM must satisfy (`VERDICT_SCHEMA`, in `prompts.py`) mirrors `Verdict`'s
judged fields: `stale` (bool), `confidence` (number), `reason` (string),
`wrong_claims` (array of strings). `additionalProperties: false`, all required.

---

## 5. Prompt design (`src/llm/prompts.py`)

- **System prompt:** frames the model as a precise technical-documentation reviewer; asks
  it to decide whether the doc section is factually contradicted by the code change, to be
  conservative (only flag stale when a concrete claim is now wrong), and to return the
  structured verdict. Explicitly: renamed/removed/re-signatured symbols the doc still
  describes = stale; behavior-neutral refactors = not stale.
- **User prompt builder** `build_staleness_prompt(input) -> str`: includes the change kind,
  the symbol name, the old code and new code (or a note that one side is absent), and the
  doc-section text — clearly delimited.
- `VERDICT_SCHEMA` constant (see §4).

---

## 6. CLI + first-class free demo

- **`docsmith investigate --repo . --base X --head Y [--index .docsmith/index.json]
  [--config configs/base.yaml] [--backend fake|ollama|claude] [--model ...]`** — runs
  detection + investigation via the chosen backend (default from config = `ollama`), prints
  per-section verdicts, e.g.:
  ```
  STALE (0.90) README.md#users — create_user
    - "create_user(name)" — signature now takes (name, email)
  OK          README.md#formatting — formatName
  ```
- **Front-door demo (first-class):** a `make investigate-demo` target (and a README
  "run this to see real verdicts" section) that builds an index on the bundled fixture
  repo, makes a scripted code change, and runs `docsmith investigate --backend ollama`
  end-to-end on the local model — **$0**. This is the documented path for the demo video
  and for any reviewer.

---

## 7. Error handling

- A single suspect whose LLM response is missing/invalid JSON or fails schema validation is
  **skipped** (counted in `InvestigationResult.skipped["llm_error"]`), logged, and does not
  abort the batch.
- Backend-unavailable errors are explicit and actionable: `OllamaClient` raising because
  Ollama isn't running surfaces a clear "start Ollama / `ollama pull <model>`" message;
  `ClaudeClient` raising for a missing key surfaces "set ANTHROPIC_API_KEY or use
  `--backend ollama`". These are raised (not silently swallowed) at the CLI boundary.

---

## 8. Config (`configs/base.yaml`, extends the existing `llm:` block)

```yaml
llm:
  backend: ollama                 # fake | ollama | claude  (default: free local model)
  ollama_model: qwen2.5-coder:7b
  ollama_host: http://localhost:11434
  claude_model: claude-sonnet-5   # only used when backend: claude + ANTHROPIC_API_KEY set
```

`load_settings` (Week 3) is extended to read these into `Settings` (with defaults). The old
`max_investigator_tool_calls` key is unused for now (single-prompt design) and left as-is.

---

## 9. Testing (default suite offline / $0)

- **Unit:**
  - `FakeLLMClient` returns its scripted dict; `complete_json` contract.
  - `build_staleness_prompt` produces a prompt containing the old code, new code, doc text,
    and change kind (exact-substring assertions); `VERDICT_SCHEMA` shape.
  - `Verdict` parsing/validation: a valid dict → `Verdict`; a malformed dict → skip.
  - `OllamaClient` with its HTTP boundary **mocked** (monkeypatched): asserts it posts to
    `{host}/api/chat` with the schema in `format` and parses the reply.
  - `ClaudeClient` with the `anthropic` SDK boundary **mocked**: asserts it calls
    `messages` with `output_config.format` = schema and parses the reply. (No real key.)
  - Input assembly: a suspect + `FileChange` + fixture index → correct `InvestigationInput`
    (old/new code sliced by symbol, doc text from the index; `None` sides for added/removed).
- **Integration (Fake backend):** full `investigate_pr` on a temp git repo + built index
  with a `FakeLLMClient` scripted to return `stale=True` for the changed symbol — asserts
  the verdict maps back to the right section and names the wrong claim, and that the CLI
  prints it. Runs in CI ($0).
- **Gated real-Ollama test (REQUIRED task, run locally):** the full pipeline against a real
  local model, skipped unless `DOCSMITH_RUN_OLLAMA_TESTS=1` and Ollama is reachable —
  asserts the real model flags a genuinely-stale fixture (`stale is True`) and does **not**
  flag an unrelated fresh section. Not run in CI; the implementer runs it locally to prove
  the real path works.
- **Gated real-Claude test:** analogous, skipped unless an API key **and**
  `DOCSMITH_RUN_MODEL_TESTS=1` — provided for completeness, not required to run.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Fake tests don't prove real judgment quality | The gated real-Ollama test + the `make investigate-demo` front door exercise the real model locally (both free); the fake suite only proves plumbing (explicitly). |
| Local model returns non-schema JSON | Ollama's `format`=JSON-schema constrains output; per-suspect validation + skip keeps one bad reply from aborting the batch. |
| Small local model gives weak verdicts | Model is configurable; default `qwen2.5-coder:7b` (code-capable). `ClaudeClient` is the drop-in upgrade for anyone with a key. Verdict quality is measured in the Week-6 evaluation. |
| Old/new source extraction misaligns with the changed symbol | Re-parse both sides with `parse_source` and select by `qualified_name`; unit-tested against fixtures. |
| Ollama not installed on a reviewer's machine | README documents `ollama pull <model>`; `--backend fake` still runs the pipeline offline with canned verdicts for a no-install smoke run. |

---

## 11. Definition of Done

- `docsmith investigate --backend ollama` produces real staleness verdicts for a real git
  range on a local model, at $0.
- `LLMClient` seam with `FakeLLMClient`, `OllamaClient`, `ClaudeClient`; importing modules
  needs no SDK/key/network.
- Single-prompt structured verdict; malformed replies skipped, not fatal.
- `make investigate-demo` runs the free end-to-end demo; README documents it.
- Default `pytest` suite is fully offline ($0) and green; `ruff check .` clean.
- The gated real-Ollama test exists and passes when run locally with Ollama.
