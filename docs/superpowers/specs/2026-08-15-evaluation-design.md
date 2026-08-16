# Evaluation & Polish (Week 6) — Design Spec

**Date:** 2026-08-15
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** the full pipeline (Weeks 1–5 + LLM Staleness Investigator), all merged to `main`.

---

## 1. Goal & Scope

Prove Docsmith works with **credible, reproducible numbers**, and publish them. Two benchmarks
share one scoring core:

- **Curated labeled corpus (the headline, reproducible):** a version-pinned set of replay
  cases bundled in the repo. Produces detection precision / recall / F1 (the published
  number) plus a secondary correction-quality score.
- **History-replay harness (real-world corroboration):** mine a *pinned* external,
  well-documented library repo for commits that changed code **and** its docs together;
  replay each (hide the doc edit, feed the code diff, measure whether the tool reproduces the
  fix). Same metrics, reported as real-world corroboration.

Plus a reporting step that aggregates a run into a markdown metrics table written into the
top-level README ("## Results").

This is the final sub-project. It completes §6 of the master design spec.

**In scope:** case format + curated corpus + loader; a scoring module (detection metrics +
correction quality); a runner that replays cases through the existing pipeline; the
history-replay mining harness; a `docsmith evaluate` CLI; `report.py` aggregation + README
publish.

**Out of scope (manual, stretch):** the demo video and Marketplace publish — noted in the
README, not built here.

**Non-goals:** No new detection/repair logic — evaluation only *measures* the existing
pipeline. No paid API: everything runs at **$0** on local Ollama.

---

## 2. Cost posture (a hard requirement, carried over) + the CI boundary

Evaluation is the one subsystem that needs **real model output** to measure quality, so the
metric-generating runs are **not** part of `pytest` CI. The split (same seam pattern as the
rest of the project):

- **Harness/scoring/mining/report LOGIC** is pure and **unit-tested offline** with
  `FakeLLMClient` + fixtures — runs in CI on every commit, **$0**, no network/LLM.
- **The actual metric-generating runs** use real **Ollama** locally (**$0**), invoked via
  `make eval` / `docsmith evaluate`, never in CI.
- Claude remains opt-in (`--backend claude`); never required, never in the default suite.

Importing any evaluation module must not require a network call, a key, or the `anthropic`
SDK.

---

## 3. Architecture & data flow

```
Corpus:  curated cases (bundled)   |   mined history cases (from a pinned repo)
   each Case: base repo state + code change (base→head) + gold labels
              gold = { stale_section_ids: set[str],  fixes: {section_id: expected_text} }
      │  runner.evaluate_cases(cases, client)     ← reuses run_detection → investigate → repair
      ▼
   per case →  Prediction { flagged_section_ids: set[str],  proposed_fixes: {section_id: text} }
      │  scoring.score_case(prediction, gold)
      ▼
   CaseResult { tp, fp, fn, correction_scores }  → scoring.aggregate(...)
      ▼
   MetricsReport { precision, recall, f1, exact_match_rate, mean_similarity, n_cases, ... }
      ▼
   report.render(report) → markdown table → written into README "## Results"
```

The runner reuses the merged pipeline components unchanged; evaluation adds only measurement.

---

## 4. Case format & corpus (`evaluation/corpus.py`, `evaluation/data/curated/`)

- **`Case`** (frozen): `case_id: str`, `repo_path: str` (a self-contained git repo dir under
  `evaluation/data/curated/<case_id>/`), `base: str`, `head: str` (git refs), and `gold: Gold`.
  The runner builds the index for the case's repo at run time (it does not ship prebuilt) — the
  index is built from the **base** revision's docs (the pre-edit state the tool is allowed to
  see), with the embedding flag injected (`embeddings=False` in offline tests).
- **`Gold`** (frozen): `stale_section_ids: frozenset[str]` (sections that *should* be flagged),
  `fixes: dict[str, str]` (section_id → expected corrected text; may be empty for cases that
  only test detection). A case with an empty `stale_section_ids` is a **negative** (a
  behavior-neutral change that must NOT be flagged) — required for measuring precision.
- **`load_curated_cases(root="evaluation/data/curated") -> list[Case]`** — each case dir holds
  a small git repo (base + head commits) and a `gold.json`. The loader reads `gold.json` and
  returns `Case`s. A `README` in the curated dir documents how to add a case.
- The curated corpus ships **~10–15 hand-authored cases** spanning: signature changes (should
  flag), renames/removals (should flag), behavior-neutral refactors (should NOT flag),
  comment/whitespace-only changes (should NOT flag), and multi-language coverage
  (Python/TS/Go). Authored during implementation; the plan specifies the exact starter set.

---

## 5. Scoring (`evaluation/scoring.py`, pure — offline-tested)

- **Detection (headline):** `score_detection(predicted: set[str], gold: set[str]) -> (tp, fp,
  fn)`; `aggregate_detection(list_of_tp_fp_fn) -> (precision, recall, f1)` with the standard
  formulas and 0-guards (precision/recall = 0.0 when the denominator is 0).
- **Correction quality (secondary):** `score_correction(predicted_text, gold_text) ->
  {exact: bool, similarity: float}`. `exact` = normalized-string equality (strip + collapse
  whitespace). `similarity` = embedding cosine similarity via the existing `Embedder` seam
  (real `BgeSmallEmbedder` in a live run; `FakeEmbedder` in offline tests). Aggregate →
  `exact_match_rate`, `mean_similarity` over correctly-flagged sections that had a gold fix.
- **`MetricsReport`** (frozen dataclass): `n_cases`, `tp`, `fp`, `fn`, `precision`, `recall`,
  `f1`, `n_corrections`, `exact_match_rate`, `mean_similarity`, `backend`, `model`, `suite`.
- All scoring is pure over predicted/gold inputs → fully unit-tested offline.

---

## 6. Runner (`evaluation/runner.py`)

- **`evaluate_cases(cases: list[Case], client: LLMClient, *, embedder: Embedder | None = None,
  repair: bool = True, embeddings: bool = True) -> list[CaseResult]`** — for each case: build
  the index from the case repo's **base** revision (docs pre-edit), then run `run_detection`
  (base→head) → `build_investigation_inputs` → `investigate` to get verdicts (predicted flagged
  = stale-verdict section ids); when `repair` and gold fixes exist, run the repair stage to get
  `proposed_fixes`. Score against `gold` via `scoring`. Client, embedder, and the `embeddings`
  flag are injected so tests run offline with fakes (`embeddings=False`).
- **`CaseResult`** (frozen): `case_id`, `tp`, `fp`, `fn`, `correction_scores: list[dict]`.
- A case whose pipeline raises (e.g. a malformed fixture) is recorded as a scored miss, not a
  crash — one bad case never aborts the batch (mirrors the investigator/repair skip rule).

---

## 7. History-replay mining (`evaluation/history_replay/mine.py`)

- **`mine_cases(repo_path: str, base: str, head: str, *, max_cases: int | None = None) ->
  list[Case]`** — walk `git log base..head`; for each commit that touched **both** a code file
  and a doc file, apply a **coupling filter**: keep the commit only if the doc edit references
  (by name) a symbol that changed in the same commit (reuse the detection/parsing layer to
  extract changed symbols + doc references). For a kept commit `C` with parent
  `P`, synthesize a `Case` with `base = P` and a `head` tree that applies **only C's code
  changes on top of P** (P's docs left intact) — so the tool, whose index is built from the
  base docs, replays the code change against the **pre-edit docs** and never sees C's doc
  edit. The **gold** is C's actual doc edit: the doc sections C changed = `stale_section_ids`,
  their post-edit text = `fixes`. Concretely the miner materializes the base and the
  code-only-head into a scratch git repo (two commits) so the existing `run_detection` path
  works unchanged. The source repo is checked out at a **pinned SHA range** for reproducibility.
- Pure git/parsing logic (no LLM) → the coupling filter and case synthesis are unit-tested on
  a small fixture git repo; the actual mining of a large external repo is a manual step.
- Documented default target: a pinned commit range of a well-documented library (chosen during
  implementation); the harness accepts any repo path + range.

---

## 8. CLI (`docsmith evaluate`)

`docsmith evaluate --suite curated|history [--repo PATH --base REF --head REF]
[--backend fake|ollama|claude] [--model ...] [--no-repair] [--out evaluation/data/runs/<ts>.json]`:
- `--suite curated` loads the bundled corpus; `--suite history` mines `--repo`/`--base`/`--head`.
- Runs `evaluate_cases`, aggregates to a `MetricsReport`, prints the table, and writes the
  full run (per-case results + report) as JSON to `--out` (default under
  `evaluation/data/runs/`, git-ignored). Exit 0. Backend-unavailable errors surface clearly and
  exit non-zero (the established rule).

---

## 9. Reporting (`evaluation/report.py`, pure — offline-tested)

- **`load_run(path) -> MetricsReport`** / **`render_table(report) -> str`** — build a markdown
  metrics table (detection P/R/F1, correction exact-match-rate + mean-similarity, N cases,
  backend/model, date).
- **`update_readme(readme_path, table, marker="<!-- docsmith:results -->")`** — insert/replace
  a marked "## Results" block in the top-level README (idempotent, like the summary-comment
  marker). Pure over its string inputs → unit-tested.
- A `make eval-report` target (or `docsmith evaluate` `--out` + a `report` subcommand) wires a
  run JSON → README update.

---

## 10. Testing ($0/offline in CI)

- **Scoring:** TP/FP/FN and precision/recall/F1 on synthetic predicted/gold (incl.
  all-empty, all-miss, perfect); correction exact/similarity with a `FakeEmbedder`.
- **Corpus loader:** a fixture curated case dir → correct `Case`/`Gold`.
- **Runner:** a tiny curated case + `FakeLLMClient` (scripted stale verdict + rewrite) +
  `FakeEmbedder` → correct `CaseResult` (predicted flagged matches, correction scored); a
  negative case (fake returns not-stale) → no false positive.
- **Mining:** a fixture git repo with one coupled code+doc commit and one uncoupled → the
  coupling filter keeps exactly the coupled one and synthesizes the right `gold`.
- **Report:** a fixture run JSON → expected markdown table; `update_readme` inserts then
  idempotently replaces the marked block.
- The real numbers come from manual `make eval` runs on Ollama (documented), never CI.

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Local 7B model produces weak corrections → unflattering correction-quality numbers | Detection P/R/F1 is the headline (the tool's core value); correction quality is clearly secondary and reported honestly. Claude is the drop-in upgrade for anyone with a key. |
| History-replay ground truth is noisy (code + docs changed for unrelated reasons) | Coupling filter (doc edit must reference a changed symbol); curated corpus is the reproducible headline, history-replay is corroboration. |
| Non-reproducible headline number | The headline comes from the version-pinned curated corpus committed in the repo; history mining uses a pinned SHA range. |
| Evaluation accidentally runs in CI (cost/flakiness) | Evaluation modules are never imported by the default suite's non-fixture paths; real runs are manual via `make eval`; only offline fake-backed logic tests run in CI. |
| Embedding model download in offline tests | Correction-similarity tests use `FakeEmbedder`; the real `BgeSmallEmbedder` is used only in live runs (already baked into the image / cached locally). |

---

## 12. Definition of Done

- `docsmith evaluate --suite curated --backend ollama` produces reproducible detection
  precision/recall/F1 + correction-quality on the bundled corpus, at **$0**.
- The history-replay harness mines a pinned external repo's code+doc commits and replays them,
  reporting the same metrics.
- `report.py` renders a metrics table and publishes it to the README "## Results" section.
- The default `pytest` suite stays fully offline ($0) and green; `ruff check .` clean; no
  evaluation code runs a real LLM in CI.
- The README documents how to reproduce the numbers (`make eval`) and notes the demo-video /
  Marketplace steps as manual follow-ups.
