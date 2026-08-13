# LLM Staleness Investigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Plan style:** This is a *plan*, not the source. It specifies interfaces, behavior, and the tests to write — the implementer writes the actual code into `src/`/`tests/` during execution (TDD: failing test → implement → green → commit).

**Goal:** For each suspect doc section from the detector, get a structured staleness verdict from an LLM — behind a pluggable client seam whose default backend is a free local model (Ollama), with a scripted fake for tests and an optional Claude backend.

**Architecture:** An `LLMClient` protocol with one `complete_json(system, user, schema)` method and three implementations (`FakeLLMClient`, `OllamaClient`, `ClaudeClient`). A `StalenessInvestigator` assembles inputs from the detector's suspects + the index (doc text) + git `FileChange`s (old/new source), sends one structured-verdict prompt per suspect, and parses `Verdict`s. An `investigate` CLI ties it together; a `make investigate-demo` runs it end-to-end on the free local model.

**Tech Stack:** Python 3.11, `urllib` (stdlib, Ollama HTTP), `anthropic` SDK (optional/lazy), existing detection + index + parsing, `pytest`.

## Global Constraints

- **Cost:** the default `pytest` suite and all CI must run **offline at $0** — only `FakeLLMClient`. No test may require a network call, an Ollama instance, or an API key unless gated behind an env var (`DOCSMITH_RUN_OLLAMA_TESTS=1` / `DOCSMITH_RUN_MODEL_TESTS=1`) and skipped by default.
- **Lazy deps:** importing any `src/` module must not import `anthropic`, open a socket, or require a key. Real backends do their heavy import/connection inside the call.
- **Commits:** short summary line; **no LLM/AI attribution anywhere** (no `Co-Authored-By`).
- **Style:** `ruff` line-length 100; functions have docstrings. Use `python3` / `python3 -m pytest`.
- **Living docs:** the controller updates `docs/planning/roadmap.md` + `CHANGELOG.md`; task implementers do NOT touch them.
- **Default backend:** `ollama`.

---

## Data Contracts (fixed up front)

- **`Verdict`** (frozen dataclass, `src/detection/models.py`): `symbol_id: str`, `section_id: str`, `stale: bool`, `confidence: float`, `reason: str`, `wrong_claims: tuple[str, ...]`.
- **`InvestigationInput`** (frozen): `symbol_id: str`, `section_id: str`, `change_kind: ChangeKind`, `symbol_name: str`, `old_code: str | None`, `new_code: str | None`, `doc_section_text: str`.
- **`InvestigationResult`** (mutable dataclass, `default_factory`): `verdicts: list[Verdict]`, `skipped: dict[str, int]`.
- **`LLMClient`** (`typing.Protocol`, `src/llm/client.py`): `complete_json(self, system: str, user: str, schema: dict) -> dict`.
- **`VERDICT_SCHEMA`** (`src/llm/prompts.py`): JSON-schema dict with properties `stale` (boolean), `confidence` (number), `reason` (string), `wrong_claims` (array of string); `required` = all four; `additionalProperties: false`.
- **`build_staleness_prompt(input: InvestigationInput) -> str`** and **`SYSTEM_PROMPT: str`** (`src/llm/prompts.py`).
- **`build_investigation_inputs(suspects: list[Suspect], file_changes: list[FileChange], index: Index) -> list[InvestigationInput]`** (`src/detection/investigator.py`).
- **`investigate(inputs: list[InvestigationInput], client: LLMClient) -> InvestigationResult`** (`src/detection/investigator.py`).
- **`run_detection(repo_root, base, head, index_path, settings) -> tuple[DetectionResult, list[FileChange]]`** and **`detect(...) -> DetectionResult`** (`src/detection/detector.py`).
- **`investigate_pr(repo_root, base, head, index_path, settings, client: LLMClient) -> InvestigationResult`** (`src/detection/investigator.py`).
- **`Settings`** gains: `llm_backend: str` (`"fake"|"ollama"|"claude"`, default `"ollama"`), `ollama_model: str`, `ollama_host: str`, `claude_model: str`.

---

## Task 0: Config — LLM settings

**Files:** Modify `src/utils/config.py`, `configs/base.yaml`; test `tests/unit/test_config.py` (extend).

**Interfaces — Produces:** `Settings` fields `llm_backend`, `ollama_model`, `ollama_host`, `claude_model`.

**Behavior:** Extend `Settings` and `load_settings` to read a `llm:` block: `backend`→`llm_backend` (default `"ollama"`), `ollama_model` (default `"qwen2.5-coder:7b"`), `ollama_host` (default `"http://localhost:11434"`), `claude_model` (default `"claude-sonnet-5"`). Missing keys → defaults (same null-safe handling as the existing loader). Add the `llm.backend`/`ollama_model`/`ollama_host`/`claude_model` keys to `configs/base.yaml` under the existing `llm:` block.

**Tests (failing first):** `load_settings()` on the real `configs/base.yaml` returns `llm_backend == "ollama"`, `ollama_model == "qwen2.5-coder:7b"`, `claude_model == "claude-sonnet-5"`; a tmp yaml with no `llm:` block returns those defaults without raising; `overrides={"llm_backend": "fake"}` is honored.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → `ruff check` both files → commit (`feat: add LLM backend settings to config`).

---

## Task 1: Investigator data models

**Files:** Modify `src/detection/models.py`; test `tests/unit/test_detection_models.py` (extend).

**Interfaces — Produces:** `Verdict`, `InvestigationInput`, `InvestigationResult` (see Data Contracts). Consumes: existing `ChangeKind`.

**Behavior:** Add the three types. `Verdict`/`InvestigationInput` are `@dataclass(frozen=True)` (hashable); `InvestigationResult` is mutable with `default_factory` for `verdicts` (list) and `skipped` (dict). `from __future__ import annotations`. Pure data, no logic. Docstrings per the house style (`Changes` in `hashing.py`).

**Tests (failing first):** construct a `Verdict` (stale True, `wrong_claims=("x",)`) and assert fields + hashability; construct an `InvestigationInput` with `old_code=None` (added-symbol case) and assert fields; `InvestigationResult()` defaults `verdicts == []`, `skipped == {}`.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: add investigator data models`).

---

## Task 2: `LLMClient` protocol + `FakeLLMClient`

**Files:** Modify `src/llm/client.py` (stub); test `tests/unit/test_llm_client_fake.py`.

**Interfaces — Produces:** `LLMClient` protocol (`complete_json(system, user, schema) -> dict`); `FakeLLMClient`.

**Behavior:** `LLMClient` is a `@runtime_checkable typing.Protocol` with `complete_json`. `FakeLLMClient` is constructed with either a fixed `dict` response or a callable `Callable[[str], dict]` mapping the `user` prompt to a response; `complete_json` returns it (ignoring `schema`, or optionally recording the last `(system, user, schema)` for assertions). No I/O, no imports beyond stdlib/typing. `from __future__ import annotations`.

**Tests (failing first):** `FakeLLMClient({"stale": True, ...}).complete_json("s", "u", {})` returns that dict; the callable form maps different `user` prompts to different dicts; `isinstance(FakeLLMClient(...), LLMClient)` is True (runtime_checkable); constructing/​importing does not import `anthropic` (assert `"anthropic" not in sys.modules` after importing the module).

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: LLMClient protocol and fake client`).

---

## Task 3: Prompts + `VERDICT_SCHEMA`

**Files:** Modify `src/llm/prompts.py` (stub); test `tests/unit/test_prompts.py`.

**Interfaces — Consumes:** `InvestigationInput`. **Produces:** `SYSTEM_PROMPT`, `VERDICT_SCHEMA`, `build_staleness_prompt(input) -> str`.

**Behavior:** `SYSTEM_PROMPT` frames a precise technical-doc reviewer: decide whether the doc section is factually contradicted by the code change; be conservative (flag stale only when a concrete claim is now wrong); renamed/removed/re-signatured symbols the doc still describes → stale; behavior-neutral refactors → not stale; return the structured verdict. `build_staleness_prompt` renders the change kind, symbol name, old code and new code (with an explicit note when a side is `None`), and the doc-section text in clearly delimited sections. `VERDICT_SCHEMA` per Data Contracts.

**Tests (failing first):** for an `InvestigationInput` (SIGNATURE_CHANGED, old/new code, doc text), `build_staleness_prompt` output contains the symbol name, both code snippets, the doc text, and the change kind; for an added-symbol input (`old_code=None`) it contains a "no previous version"-style note and does not crash; `VERDICT_SCHEMA` has the four required properties and `additionalProperties is False`.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: staleness prompt and verdict schema`).

---

## Task 4: Detector refactor — `run_detection`

**Files:** Modify `src/detection/detector.py`; test `tests/integration/test_detector.py` (extend); existing Week-3 detector tests must stay green.

**Interfaces — Produces:** `run_detection(repo_root, base, head, index_path, settings) -> tuple[DetectionResult, list[FileChange]]`; `detect(...)` unchanged externally (now a wrapper).

**Behavior:** Extract the current `detect` body into `run_detection`, which returns both the `DetectionResult` and the `file_changes` it collected from `collect_changes`. `detect(...)` calls `run_detection` and returns only the `DetectionResult` — its signature and behavior are unchanged. No second git pass.

**Tests (failing first):** on the temp-git-repo fixture used by the existing detector test, `run_detection(...)` returns a `DetectionResult` equal in content to `detect(...)` and a non-empty `file_changes` list that includes the changed code file with both `old_content` and `new_content`. Existing `test_detector.py` cases still pass unchanged (regression guard).

**Steps:** failing test → run (fail) → refactor → run new + existing detector tests (pass) → full suite green → ruff → commit (`refactor: expose file changes via run_detection`).

---

## Task 5: Input assembly — `build_investigation_inputs`

**Files:** Modify `src/detection/investigator.py` (stub); test `tests/unit/test_investigation_inputs.py`.

**Interfaces — Consumes:** `Suspect`, `FileChange`, `Index`, `ChangedSymbol` ids, `parse_source`, `language_for_path`. **Produces:** `build_investigation_inputs(suspects, file_changes, index) -> list[InvestigationInput]`.

**Behavior:** Build `path -> FileChange` and use `index.sections` for doc text. For each suspect: the doc-section text is `index.sections[section_id].raw` (skip a suspect whose `section_id` is absent from the index). Derive the symbol's file + qualified name from `symbol_id` (which is `"{file}::{qualified_name}"`). Extract old/new source by `parse_source(fc.old_content, file, language)` / `parse_source(fc.new_content, file, language)` (when that content is present), selecting the `Symbol` whose `qualified_name` matches, and slicing its `start_line..end_line` from the corresponding content lines; `old_code`/`new_code` are `None` when that side's content is absent or the symbol isn't found on that side. Populate `symbol_name` (bare name = last dotted component of the qualified name). Dedup per `(symbol_id, section_id)`, deterministic order (input order).

**Tests (failing first):** hand-build a small `Index` (one `DocSection`) + a `FileChange` (old/new Python content defining `def foo(x):`→`def foo(x, y):`) + a `Suspect` referencing `m.py::foo` and that section → one `InvestigationInput` with `old_code` containing `def foo(x)`, `new_code` containing `def foo(x, y)`, `doc_section_text` from the index, `symbol_name == "foo"`. A REMOVED-symbol suspect (new_content lacks the symbol) → `new_code is None`. A suspect whose `section_id` isn't in the index → omitted.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: assemble investigation inputs from suspects and diffs`).

---

## Task 6: Investigator core — `investigate`

**Files:** Modify `src/detection/investigator.py`; test `tests/unit/test_investigator.py`.

**Interfaces — Consumes:** `InvestigationInput`, `LLMClient`, `build_staleness_prompt`, `SYSTEM_PROMPT`, `VERDICT_SCHEMA`, `Verdict`, `InvestigationResult`. **Produces:** `investigate(inputs, client) -> InvestigationResult`.

**Behavior:** For each input: `client.complete_json(SYSTEM_PROMPT, build_staleness_prompt(input), VERDICT_SCHEMA)`; validate the returned dict has `stale` (bool), `confidence` (number coerced to float), `reason` (str), `wrong_claims` (list of str); build a `Verdict` carrying the input's `symbol_id`/`section_id`. If the dict is missing keys / wrong types / the call raised, increment `result.skipped["llm_error"]`, log a one-line warning, and continue. Return the `InvestigationResult`.

**Tests (failing first):** with a `FakeLLMClient` returning a valid verdict dict, `investigate([input], fake)` → one `Verdict` with the right `section_id`/`stale`/`wrong_claims`, `skipped == {}`. With a `FakeLLMClient` returning a malformed dict (missing `stale`), → `verdicts == []`, `skipped == {"llm_error": 1}` (batch not aborted). With a callable fake returning valid for one input and malformed for another → one verdict + one skip.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: staleness investigator core`).

---

## Task 7: `OllamaClient`

**Files:** Modify `src/llm/client.py`; test `tests/unit/test_ollama_client.py`.

**Interfaces — Produces:** `OllamaClient(model: str, host: str)` implementing `LLMClient`.

**Behavior:** `complete_json` POSTs JSON to `{host}/api/chat` via `urllib.request` (stdlib — no new dependency) with body `{"model": model, "messages": [{"role":"system","content":system},{"role":"user","content":user}], "format": schema, "stream": false, "options": {"temperature": 0}}`. Parse the response JSON, read `message.content` (a JSON string), `json.loads` it, and return the dict. On a connection error (Ollama not running), raise a clear `RuntimeError` telling the user to start Ollama / `ollama pull <model>`. Lazy: `urllib` import at module top is fine (stdlib); no `anthropic`.

**Tests (failing first):** monkeypatch the HTTP call (patch `urllib.request.urlopen`, or a small internal `_post` seam) to return a canned Ollama reply whose `message.content` is `'{"stale": true, "confidence": 0.9, "reason": "...", "wrong_claims": ["..."]}'`; assert `complete_json` returns the parsed dict AND that the request body sent included `format` == the schema and both system+user messages. Simulate a connection error → asserts a `RuntimeError` mentioning Ollama. (No real Ollama contacted.)

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: Ollama LLM backend`).

---

## Task 8: `ClaudeClient`

**Files:** Modify `src/llm/client.py`; test `tests/unit/test_claude_client.py`.

**Interfaces — Produces:** `ClaudeClient(model: str = "claude-sonnet-5")` implementing `LLMClient`.

**Behavior:** `complete_json` **lazy-imports** `anthropic` inside the method, constructs `anthropic.Anthropic()` (resolves key from env), and calls `messages.create(model=self.model, max_tokens=1024, system=system, messages=[{"role":"user","content":user}], output_config={"format": {"type": "json_schema", "schema": schema}})`; reads the first `text` content block, `json.loads` it, returns the dict. A missing/invalid key surfaces a clear `RuntimeError` ("set ANTHROPIC_API_KEY or use --backend ollama"). Importing `src/llm/client.py` must NOT import `anthropic`.

**Tests (failing first):** assert `"anthropic" not in sys.modules` after `import src.llm.client` (import-guard). Then monkeypatch the lazy import boundary — patch a small internal `_anthropic_client()` factory (or `sys.modules["anthropic"]`) with a fake whose `messages.create(...)` returns an object with a text block containing valid verdict JSON; assert `complete_json` calls it with `output_config.format` == the schema and `model == "claude-sonnet-5"`, and returns the parsed dict. (No real key, no network.)

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: Claude LLM backend`).

---

## Task 9: Orchestrator + `investigate` CLI

**Files:** Modify `src/detection/investigator.py` (add `investigate_pr` + a `make_client` factory), `docsmith.py`; test `tests/integration/test_cli_investigate.py`.

**Interfaces — Consumes:** `run_detection`, `build_investigation_inputs`, `investigate`, `Settings`, the three clients. **Produces:** `investigate_pr(repo_root, base, head, index_path, settings, client) -> InvestigationResult`; a `make_client(settings, backend_override=None) -> LLMClient` factory (maps `"fake"|"ollama"|"claude"` → the client; `"fake"` yields a `FakeLLMClient` with a benign default only for the CLI's internal use/tests); the `investigate` CLI subcommand.

**Behavior:** `investigate_pr` = `run_detection` → `build_investigation_inputs(result.suspects, file_changes, load_index(index_path))` → `investigate(inputs, client)`. CLI `docsmith investigate --repo --base --head [--index] [--config] [--backend] [--model]`: load settings, pick backend (`--backend` overrides `settings.llm_backend`; `--model` overrides the backend's model), build the client via `make_client`, run `investigate_pr`, and print verdicts grouped/one-per-line (`STALE (0.90) <section_id> — <symbol_name>` + each wrong claim; `OK <section_id> — <symbol_name>` for not-stale) plus a trailing `(N skipped)` if any. Exit 0.

**Tests (failing first), via `subprocess` on a temp git repo + built index, `--backend fake`:** the CLI test sets the backend to `fake` so it stays offline — since a real fake needs a scripted verdict, the CLI's `make_client("fake")` returns a `FakeLLMClient` that yields a fixed `stale=true` verdict; assert exit 0 and stdout contains `STALE` and the README section id. Also a unit test: `investigate_pr(..., FakeLLMClient(stale-verdict))` on the temp repo returns an `InvestigationResult` whose verdict maps to the changed symbol's section.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → `ruff check` changed files → commit (`feat: investigate CLI and orchestrator`).

---

## Task 10: Free demo + gated real-Ollama test

**Files:** Create `Makefile` (or add a target if one exists) and `scripts/dev/investigate_demo.sh`; modify `README.md`; test `tests/integration/test_investigate_ollama.py`.

**Interfaces — Consumes:** the `investigate` CLI.

**Behavior:**
- **`make investigate-demo`**: a target that (in a temp dir) copies `tests/fixtures/sample_repo`, `git init`+commit, builds the index (`docsmith build-index --no-embeddings`), makes a scripted signature change to a documented function, commits, and runs `docsmith investigate --backend ollama --base <base> --head <head>` — printing real verdicts from the local model. Zero cost. (A small shell script under `scripts/dev/` does the work; the Make target calls it.)
- **README**: a "See it work (free, local)" section documenting `ollama pull qwen2.5-coder:7b` + `make investigate-demo`, and stating the backend is pluggable (fake/ollama/claude).
- **Gated real-Ollama test** (`tests/integration/test_investigate_ollama.py`): `@pytest.mark.skipif(os.environ.get("DOCSMITH_RUN_OLLAMA_TESTS") != "1" or Ollama not reachable, ...)`. When enabled: build an index on a temp repo, make a real signature change, run `investigate_pr(..., OllamaClient(...))`, assert the changed symbol's section gets `stale is True` and an unrelated untouched section does not appear as a stale verdict. Skipped by default (CI has no Ollama).

**Tests (failing first):** the gated test is written and **collectable** (imports resolve, it SKIPS cleanly under a normal `pytest` run — assert via `-rs` that it's skipped, not errored). Verify `make investigate-demo` exists and its script is syntactically valid (`bash -n`). (Do not run the real model in CI.)

**Steps:** write the gated test (confirm it skips) → add the demo script + Make target (`bash -n` clean) → README section → full suite green (real-Ollama test SKIPPED) → `ruff check` any Python touched → commit (`feat: free local investigate demo and gated ollama test`).

---

## Definition of Done

- `docsmith investigate --backend ollama --base X --head Y` prints real staleness verdicts from a local model at $0; `make investigate-demo` runs the whole thing end-to-end free.
- `LLMClient` seam with `FakeLLMClient`, `OllamaClient`, `ClaudeClient`; importing `src/llm/client.py` imports neither `anthropic` nor opens a socket.
- Single-prompt structured verdict; malformed replies skipped (counted), never fatal.
- Default `pytest` suite fully offline ($0) and green; the gated real-Ollama test skips cleanly in CI and passes when run locally with Ollama; `ruff check .` clean.
- No LLM/AI attribution in any commit.
