# Docsmith Roadmap & Progress

Living progress tracker for the project. The authoritative design is the
[design spec](../superpowers/specs/2026-06-11-self-healing-docs-design.md); detailed,
executable task plans live in [`docs/superpowers/plans/`](../superpowers/plans/). This
file is the human-facing rollup of *where we are*.

**Status legend:** ✅ done · 🚧 in progress · ⬜ not started

**Current focus:** 🎉 **All six sub-projects complete** (Weeks 1–6 + the LLM staleness investigator). The full self-healing-docs pipeline runs end-to-end as a $0 GitHub Action with a reproducible evaluation harness. Remaining optional/stretch work: the API-reference + config/CLI/env doc extractors deferred from Week 2; a demo video; Marketplace publish.

---

## Phase 0 — Project setup ✅
- ✅ Brainstormed scope; design spec written and approved
- ✅ Repo structure scaffolded (Forge-inspired layout)
- ✅ GitHub repo created and pushed (public)
- ✅ CI workflow (ruff + pytest) green
- ✅ Living docs established (this file + `CHANGELOG.md`)

## Week 1 — Index Core ✅
Detailed plan: [2026-06-11-index-core.md](../superpowers/plans/2026-06-11-index-core.md).
**Done:** 45 tests passing, `python docsmith.py build-index` produces `.docsmith/index.json`
for Python/TS/JS/Go + markdown. Deferred to Week 2: path normalization of ids (M1) and a
stable id scheme for incremental joins.
Goal: parse a repo into code symbols + doc sections, link them by name, persist to
`.docsmith/index.json`. Pure/deterministic, zero LLM.

| Task | Description | Status |
|---|---|---|
| 0 | Pin tree-sitter deps + fixture repo | ✅ |
| 1 | Core data models (`src/models.py`) | ✅ |
| 2 | Language registry (`src/parsing/languages.py`) | ✅ |
| 3 | Code parser — Python symbols + docstrings | ✅ |
| 4 | Code parser — TS/JS/Go | ✅ |
| 5 | Doc parser — split into sections | ✅ |
| 6 | Doc parser — reference extraction | ✅ |
| 7 | Deterministic linker (`src/index/linker.py`) | ✅ |
| 8 | Index store — JSON round-trip | ✅ |
| 9 | Index builder — walk repo → parse → link | ✅ |
| 10 | `build-index` CLI subcommand | ✅ |

## Week 2 — Retrieval Core ✅
Scoped to the retrieval core (the API-reference + config/CLI/env extractors were split
out into their own later sub-project). Spec:
[2026-06-12-retrieval-core-design.md](../superpowers/specs/2026-06-12-retrieval-core-design.md);
plan: [2026-06-12-retrieval-core.md](../superpowers/plans/2026-06-12-retrieval-core.md).
**Done:** 110 tests passing (offline; real bge-small test gated behind
`DOCSMITH_RUN_MODEL_TESTS=1` and verified). Week-1 carry-over M1 (repo-relative ids)
resolved here.

| Task | Description | Status |
|---|---|---|
| 0 | CI full-suite + Node 24; `linking.top_k` config | ✅ |
| 1 | Repo-relative id normalization (`rel_path`) | ✅ |
| 2 | `Index.file_hashes` model + store round-trip | ✅ |
| 3 | File hashing + change classification | ✅ |
| 4 | Embedder seam (`Embedder`, `FakeEmbedder`, `BgeSmallEmbedder`) | ✅ |
| 5 | Cosine Chroma `VectorStore` wrapper | ✅ |
| 6 | Embedding-recall linking + hybrid merge | ✅ |
| 7 | Hybrid `build_index` (embeddings + repo-relative ids) | ✅ |
| 8 | Incremental `update_index` (content-hash) | ✅ |
| 9 | CLI: incremental-by-default, `--full`, `--no-embeddings` | ✅ |

**Deferred follow-ups (noted during review):** use stored section vectors in recall
instead of re-embedding at query time; wire `configs/base.yaml` `linking.*` into the
builder/CLI (currently hardcoded defaults match the config).

## Week 3 — Detection Core ✅
Scoped to the **deterministic** detection pipeline (the LLM staleness investigator was
split out into its own next sub-project). Spec:
[2026-06-15-detection-core-design.md](../superpowers/specs/2026-06-15-detection-core-design.md);
plan: [2026-06-15-detection-core.md](../superpowers/plans/2026-06-15-detection-core.md).
**Done:** 160 tests passing (offline). Pipeline: git adapter → diff parser → symbol mapper
(add/remove/signature/body classification) → triage → candidate linker (index-link +
name-reference) → `detect` CLI. Also added a minimal config loader (clears a Week-2 follow-up).

| Task | Description | Status |
|---|---|---|
| 0 | Minimal config loader (`src/utils/config.py`) | ✅ |
| 1 | Detection data models (`src/detection/models.py`) | ✅ |
| 2 | Content-based `parse_source` refactor | ✅ |
| 3 | Diff parser (unified diff → changed lines) | ✅ |
| 4 | Git adapter (`collect_changes`) | ✅ |
| 5 | Symbol mapper (classify changed symbols) | ✅ |
| 6 | Triage filter (drop noise) | ✅ |
| 7 | Candidate linker (suspects from index) | ✅ |
| 8 | Detector orchestrator (`detect`) | ✅ |
| 9 | `detect` CLI subcommand | ✅ |

**Known follow-ups (from review):** pure-deletion body changes aren't detected (new-file
line-number heuristic); non-ASCII filenames (git `quotepath`); candidate linker is O(n×m)
at scale; CLI loads the index twice. None blocking.

## Sub-project — LLM Staleness Investigator ✅ (first LLM integration)
Spec: [2026-08-12-llm-investigator-design.md](../superpowers/specs/2026-08-12-llm-investigator-design.md);
plan: [2026-08-12-llm-investigator.md](../superpowers/plans/2026-08-12-llm-investigator.md).
**Done:** 202 tests passing (offline). Given the detector's suspect sections, an LLM judges
whether each is actually stale (old code + new code + doc section → structured verdict +
wrong-claims), behind an `LLMClient` seam with three backends — `FakeLLMClient` (tests),
`OllamaClient` (free local model, the default), `ClaudeClient` (optional/paid). Single-prompt
structured verdict; malformed replies skipped, backend-unavailable errors surfaced. Whole
sub-project builds/tests/demos at **$0** (`make investigate-demo` runs it free on Ollama).

| Task | Description | Status |
|---|---|---|
| 0 | LLM settings in config loader | ✅ |
| 1 | Investigator data models (`Verdict`/`Input`/`Result`) | ✅ |
| 2 | `LLMClient` protocol + `FakeLLMClient` | ✅ |
| 3 | Prompts + `VERDICT_SCHEMA` | ✅ |
| 4 | Detector refactor (`run_detection` exposes `FileChange`s) | ✅ |
| 5 | Input assembly (`build_investigation_inputs`) | ✅ |
| 6 | Investigator core (`investigate`) | ✅ |
| 7 | `OllamaClient` (free local backend) | ✅ |
| 8 | `ClaudeClient` (optional/paid backend) | ✅ |
| 9 | `investigate_pr` orchestrator + `docsmith investigate` CLI | ✅ |
| 10 | Free `make investigate-demo` + gated real-Ollama test | ✅ |

**Deferred follow-ups (from final review):** guard the `symbol_id` `::` split; cache the
per-suspect source re-parse; friendlier message on a responding-but-non-JSON Ollama reply;
shared `symbol_name`-from-id helper (CLI vs. assembly); a gated real-Claude test. None blocking.

## Week 4 — Repair ✅
Spec: [2026-08-13-repair-engine-design.md](../superpowers/specs/2026-08-13-repair-engine-design.md);
plan: [2026-08-13-repair-engine.md](../superpowers/plans/2026-08-13-repair-engine.md).
**Done:** 232 tests passing (offline). Turns stale verdicts into routed doc corrections:
whole-section LLM rewrite + deterministic `difflib` diff → independent LLM validator gate →
deterministic confidence router (AUTOFIX / FLAG / NO_CHANGE). Read-only — proposes diffs, never
writes files or opens PRs (that's Week 5). Reuses the `LLMClient` seam; malformed replies
skipped, backend-unavailable errors surfaced. `make repair-demo` runs it free on Ollama at **$0**.

| Task | Description | Status |
|---|---|---|
| 0 | Repair routing settings in config | ✅ |
| 1 | Promote `extract_symbol_source` to shared `src/detection/source.py` | ✅ |
| 2 | Repair data models (`RepairInput`/`Proposal`/`ValidationResult`/`Route`/`Outcome`/`Result`) | ✅ |
| 3 | Repair + validation prompts and schemas | ✅ |
| 4 | Repair Engine (`repair_section` + computed diff) | ✅ |
| 5 | Validator (`validate_repair`) | ✅ |
| 6 | Confidence Router (`route`) | ✅ |
| 7 | Input assembly (`build_repair_inputs`) | ✅ |
| 8 | Orchestrator (`repair_pr`) | ✅ |
| 9 | `docsmith repair` CLI | ✅ |
| 10 | Free `make repair-demo` + gated real-Ollama test | ✅ |

**Deferred follow-ups (from final review):** `docsmith repair --backend fake` is degenerate
(the fixed-verdict fake gives repair no `revised_text`, so sections skip) — route the CLI fake
by prompt anchor or document it; add per-validator-flag router tests; record that the doc
parser's identifier regex doesn't link backtick tokens containing parens (e.g. `` `create_user(name)` ``);
backport the `investigate_demo.sh` unescaped-`$0` banner fix. None blocking.

## Week 5 — GitHub Action ✅
Spec: [2026-08-15-github-action-design.md](../superpowers/specs/2026-08-15-github-action-design.md);
plan: [2026-08-15-github-action.md](../superpowers/plans/2026-08-15-github-action.md).
**Done:** 259 tests passing (offline). Turns the repair engine's routed outcomes into real
GitHub output on a PR — an always-posted summary comment, one companion fix-PR for AUTOFIX
corrections (deterministic span-replace), and FLAG items rendered with collapsible proposed
diffs. **Never auto-merges.** Behind a `GitHubClient` write-side seam (`PyGithubClient` +
`FakeGitHubClient`); the default suite stays $0/offline (fake GitHub + fake LLM), and the
live Action runs at **$0** on Ollama + `github.token` (self-hosted runner). Idempotent
re-runs (marker-based comment upsert + reused `docsmith/fix-pr-{n}` branch).

| Task | Description | Status |
|---|---|---|
| 0 | `auto_fix` setting | ✅ |
| 1 | `RepairResult.verified` (accurate-section count) | ✅ |
| 2 | PR-context loader (reads the Actions event) | ✅ |
| 3 | AUTOFIX file application (bottom-up span-replace) | ✅ |
| 4 | Summary markdown builder (marker + counts + FLAG diffs) | ✅ |
| 5 | `GitHubClient` seam + `FakeGitHubClient` | ✅ |
| 6 | `PyGithubClient` (real, lazy-imported) | ✅ |
| 7 | Reporter (summary comment + companion fix-PR) | ✅ |
| 8 | `github-action` entrypoint (`run_action` + CLI + `$GITHUB_OUTPUT`) | ✅ |
| 9 | Finalize `action.yml` (key optional, `llm-backend`) + `Dockerfile` | ✅ |
| 10 | Gated live-GitHub test + "run on a real PR" README | ✅ |

**Deferred follow-ups (from final review):** narrow `PyGithubClient.open_or_update_fix_pr`'s
try/except so a mutation error isn't misread as "not found"; wrap GitHub API errors with a
clean CLI message; fix the AUTOFIX-heading label when auto-fix is on but nothing applies;
`load_pr_context` malformed-payload → `ValueError` not `KeyError`; escape triple-backticks in
rendered diffs. None blocking.

## Week 6 — Evaluation & polish ✅
Spec: [2026-08-15-evaluation-design.md](../superpowers/specs/2026-08-15-evaluation-design.md);
plan: [2026-08-15-evaluation.md](../superpowers/plans/2026-08-15-evaluation.md).
**Done:** 279 tests passing (offline). Measures the pipeline with reproducible numbers: a
version-pinned **curated corpus** (the headline — detection precision/recall/F1, plus a
secondary correction-quality score) and a real **history-replay** mining harness (coupled
code+doc commits from a pinned external repo). Cases are file-pairs materialized into scratch
git repos; detection is scored from the investigator's verdicts (independent of repair). A
`docsmith evaluate` CLI + `report.py` publish a metrics table to the README "## Results".
Harness/scoring/mining/report logic is unit-tested offline with fakes (in CI, $0); the real
numbers come from a manual `make eval` on Ollama (a gated test guards the real path).

| Task | Description | Status |
|---|---|---|
| 0 | Evaluation data models (`Gold`/`Case`/`CaseResult`/`MetricsReport`) | ✅ |
| 1 | Case materializer (file-pairs → scratch git repo; path-traversal guarded) | ✅ |
| 2 | Scoring (detection P/R/F1 + correction quality) | ✅ |
| 3 | Curated corpus + loader (4 starter cases, positives + negatives) | ✅ |
| 4 | Runner (replay + score) | ✅ |
| 5 | History-replay mining (coupled code+doc commits) | ✅ |
| 6 | `docsmith evaluate` CLI | ✅ |
| 7 | Reporting (`report.py` → README "## Results") | ✅ |
| 8 | `make eval`/`eval-report`, README, gated real-Ollama eval test | ✅ |

**Deferred follow-ups (from final review):** whitespace-collapse in correction scoring could
mask multi-line differences (secondary metric); `corpus.py` `open()` encoding; mining
first-parent diff on merge commits. Manual stretch items not built: demo video, Marketplace
publish. None blocking.

---

## Project status — all six sub-projects complete ✅
Docsmith runs end-to-end as a GitHub Action: parse → index → detect changed symbols → LLM
staleness verdict → repair + validate + confidence-route → summary comment + companion
fix-PR, at **$0** on local Ollama, never auto-merging. **279 tests passing offline; `ruff`
clean.** Reproduce the evaluation numbers with `make eval && make eval-report`.
