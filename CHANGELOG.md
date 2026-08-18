# Changelog

All notable changes to Docsmith are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project predates its first
release; everything lives under **Unreleased** until then.

## [Unreleased]

### Added
- **Web Playground** — a $0, read-only web demo: paste a public GitHub PR URL, get
  Docsmith's staleness verdicts + proposed fix diffs, no install required. Decoupled
  backend/frontend that deploy separately; `src/` is untouched.
  - FastAPI JSON API (`webapp/`): `parse_pr_url`/`fetch_pr` (`webapp/prfetch.py`) clone a
    public PR into a scratch repo via a blobless partial clone, check out the PR head, and
    enforce a size cap (50MB) and an allowlist of `https://github.com/{owner}/{repo}/pull/{n}`
    URLs. `analyze()` (`webapp/service.py`) runs the existing `investigate_pr` + `repair_pr`
    pipeline unmodified against the checkout, joins verdicts to repair outcomes per
    `(symbol_id, section_id)`, and shapes the result as JSON. `webapp/app.py` exposes
    `GET /healthz` and `POST /api/analyze` with CORS and error mapping
    (`ValueError`→400, backend-unavailable `RuntimeError`→502, unexpected→500, credentials
    never in the response body). Requests are serialized behind an in-process lock so the
    visitor-supplied Anthropic key (set into the environment only per-request) can't leak
    across concurrent requests; an optional `GITHUB_TOKEN` raises the GitHub API rate limit.
  - React + TypeScript + Vite SPA (`frontend/`): a form (PR URL, Ollama/Claude backend
    choice, credential, optional model) posts via a typed API client
    (`frontend/src/api.ts`) and renders results (summary counts, per-section confidence,
    wrong claims, and proposed diff) via TanStack Query — Tailwind utility classes only, no
    component library.
  - `Dockerfile.web` (backend, free-tier deploy) + `frontend/vercel.json` (frontend,
    Vercel), wired via `VITE_API_BASE`/`CORS_ORIGINS`; `make api`/`make web` for local dev.
    Gated live-PR test (`DOCSMITH_RUN_WEB_LIVE=1`) + a "Try it (web playground)" README
    section covering both local and cloud deploys. 297 tests passing (offline).
- **Evaluation & Polish (Week 6)** — a reproducible benchmark harness proving the pipeline
  works, at **$0** on local Ollama (never in CI — the metric-generating runs are manual).
  - Curated corpus (`evaluation/corpus.py` + `evaluation/data/curated/*.json`): version-pinned
    replay cases (positives + negatives) → the headline **detection precision/recall/F1** plus a
    secondary correction-quality score.
  - Scoring (`evaluation/scoring.py`), case materializer (`evaluation/materialize.py`,
    file-pairs → scratch git repo with a path-traversal guard), and runner
    (`evaluation/runner.py`) that replays each case through the real pipeline — detection scored
    from the investigator's verdicts, independent of repair success.
  - History-replay mining (`evaluation/history_replay/mine.py`): synthesizes cases from a
    pinned repo's coupled code+doc commits (the doc edit is hidden and used as gold).
  - `docsmith evaluate` CLI + `evaluation/report.py` (metrics table published to the README
    "## Results" section) + `make eval`/`make eval-report`. Gated real-Ollama eval test behind
    `DOCSMITH_RUN_OLLAMA_TESTS=1`. 279 tests passing (offline).
  - **This completes the 6-part project:** parse → index → detect → LLM staleness verdict →
    repair/validate/route → GitHub summary + companion fix-PR, end-to-end at $0, never auto-merging.
- **GitHub Action (Week 5)** — turns routed repair outcomes into real GitHub output on a PR.
  Never auto-merges. Default suite stays $0/offline; the live Action runs at **$0** on Ollama
  + `github.token`.
  - `GitHubClient` write-side seam (`src/github/client.py`): `PyGithubClient` (real, lazy-
    imports PyGithub so importing needs no SDK/token) + `FakeGitHubClient` (offline tests),
    with `upsert_summary_comment` and `open_or_update_fix_pr`.
  - Reporter (`src/github/reporter.py`): posts an always-on **summary comment**, opens **one
    companion fix-PR** for AUTOFIX corrections, and lists FLAG items with collapsible proposed
    diffs. Idempotent — re-runs update the same comment (hidden `<!-- docsmith:summary -->`
    marker) and reuse the `docsmith/fix-pr-{n}` branch.
  - AUTOFIX file application (`src/github/apply.py`): deterministic span-replace, bottom-up so
    multiple edits to one file don't drift, trailing newline preserved.
  - PR-context loader (`src/github/context.py`), summary markdown builder
    (`src/github/summary.py`), and the `github-action` entrypoint (`src/github/action.py`,
    `action_settings.py`, `docsmith github-action`) wiring inputs → index → repair → report →
    `$GITHUB_OUTPUT`.
  - `Settings.auto_fix` and `RepairResult.verified` (accurate-section count) added.
  - `action.yml` finalized: `anthropic-api-key` optional; new `llm-backend` (default `ollama`)
    and `ollama-host` inputs; `fix-pr-url` output. `Dockerfile` bakes in the embedding model.
  - Gated live-GitHub test (`DOCSMITH_RUN_GITHUB_TESTS=1`) + a "run on a real PR (free,
    local)" README section. 259 tests passing (offline).
- **Repair Engine (Week 4)** — turns stale verdicts into routed doc corrections; read-only
  (no file writes / GitHub — that's Week 5). Builds, tests, and demos at **$0**.
  - Repair Engine (`src/repair/repairer.py`): `repair_section` asks the LLM to rewrite a
    stale section (whole-section rewrite, changing only what's wrong) and computes a
    deterministic unified diff via `difflib` — the diff is derived, never trusted from the
    model; a no-op rewrite yields `changed=False` / empty diff.
  - Validator (`src/repair/validator.py`): `validate_repair` — an independent LLM gate
    returning `{accurate, preserved, style_ok, notes}`.
  - Confidence Router (`src/repair/confidence_router.py`): `route` — deterministic
    AUTOFIX / FLAG / NO_CHANGE. AUTOFIX only when the validator is clean, the change is
    mechanical (`change_kind` in the configured set, default `signature_changed`), and the
    staleness confidence meets the threshold; everything else FLAGs for human review.
  - Orchestrator (`src/repair/engine.py`): `build_repair_inputs` (joins each stale verdict
    to its suspect to recover the change kind + extracts the new source) and `repair_pr`
    (detect → investigate → repair → validate → route; malformed replies skipped-and-counted,
    backend-unavailable errors propagate to the CLI).
  - Repair data models (`src/detection/models.py`): `RepairInput`, `RepairProposal`,
    `ValidationResult`, `RepairRoute`, `RepairOutcome`, `RepairResult`. Repair + validation
    prompts/schemas added to `src/llm/prompts.py`.
  - `docsmith repair` CLI (`--backend`, `--model`, `--threshold`) printing per-section
    routes + proposed diffs and a rollup; backend-unavailable errors exit non-zero.
  - Shared `src/detection/source.py` (`extract_symbol_source`, promoted from the
    investigator) reused by both stages. Repair settings in `configs/base.yaml`
    (`repair.confidence_threshold`, `repair.autofix_change_kinds`).
  - `make repair-demo` + `scripts/dev/repair_demo.sh` — a free, local end-to-end demo;
    README "See it fix docs (free, local)". Gated real-Ollama repair test behind
    `DOCSMITH_RUN_OLLAMA_TESTS=1`. 232 tests passing (offline).
- **LLM Staleness Investigator** — the first LLM stage: turns the detector's suspect
  doc sections into structured staleness verdicts. Builds, tests, and demos at **$0**.
  - `LLMClient` seam (`src/llm/client.py`): a provider-neutral
    `complete_json(system, user, schema) -> dict` protocol with three backends —
    `FakeLLMClient` (scripted, offline, for tests), `OllamaClient` (free local model via
    the Ollama HTTP API — the **default**), and `ClaudeClient` (optional/paid Anthropic
    SDK, lazy-imported so importing the module never needs the SDK, a key, or a socket).
  - Prompts + schema (`src/llm/prompts.py`): `SYSTEM_PROMPT`, `VERDICT_SCHEMA`, and
    `build_staleness_prompt` (renders change kind, symbol name, old/new code, doc text).
  - Investigator (`src/detection/investigator.py`): `build_investigation_inputs`
    (assembles per-suspect evidence, re-parsing old/new source by symbol),
    `investigate` (single-prompt structured verdict per suspect; malformed/invalid
    replies are skipped and counted, while backend-unavailable errors propagate),
    `investigate_pr` (end-to-end orchestrator), and a `make_client` backend factory.
  - Investigator data models (`src/detection/models.py`): `Verdict`,
    `InvestigationInput`, `InvestigationResult`. Detector now exposes `run_detection`
    (returns the `FileChange`s alongside the `DetectionResult`).
  - `docsmith investigate` CLI (`--backend fake|ollama|claude`, `--model`) printing
    per-section `STALE`/`OK` verdicts; backend-unavailable errors surface a clear
    message and a non-zero exit.
  - `make investigate-demo` + `scripts/dev/investigate_demo.sh` — a free, local,
    end-to-end demo on the bundled fixture repo; README "See it work (free, local)".
  - LLM settings in `configs/base.yaml` (`backend`, `ollama_model`, `ollama_host`,
    `claude_model`). Default `pytest` suite stays fully offline; a real-Ollama test is
    gated behind `DOCSMITH_RUN_OLLAMA_TESTS=1`. 202 tests passing (offline).
- **Detection Core (Week 3)** — deterministic, zero-LLM PR-diff → suspect-doc pipeline:
  - Minimal config loader (`src/utils/config.py`) reading `configs/base.yaml`.
  - Content-based `parse_source` extracted from `parse_file` (parses in-memory content).
  - Diff parser (`src/detection/diff_parser.py`) — unified diff → changed new-file lines.
  - Git adapter (`src/detection/git_adapter.py`) — `collect_changes(repo, base, head)`
    yielding `FileChange`s (old/new content + changed lines) from a ref range.
  - Symbol mapper (`src/detection/symbol_mapper.py`) — classifies changed symbols
    (added / removed / signature-changed / body-changed); renames as removed + added.
  - Triage filter (`src/detection/triage_filter.py`) — drops ignored/test paths and
    comment-only / whitespace-only changes.
  - Candidate linker (`src/detection/candidate_linker.py`) — suspect doc sections via
    index links + name references (catches removed symbols).
  - Detector orchestrator (`src/detection/detector.py`) and `docsmith detect` CLI.
  - Detection data models (`src/detection/models.py`). 160 tests passing (offline).
- **Retrieval Core (Week 2)** — embedding-based recall + incremental updates:
  - `Embedder` seam (`src/index/embeddings.py`): `Embedder` protocol, deterministic
    offline `FakeEmbedder` (for tests), and `BgeSmallEmbedder` wrapping
    `BAAI/bge-small-en-v1.5` (lazy-loaded — importing never downloads the model).
  - Cosine `VectorStore` (Chroma, file-based): per-entity vectors with `group`/`file`
    metadata, `1 - distance` similarity, delete-by-file, reset.
  - Hybrid linking (`src/index/linker.py`): `link_by_embedding` (recall) + `merge_links`
    collapsing symbol-match ∩ embedding pairs to `via="both"`.
  - Content-hash incremental updates: `Index.file_hashes`, `src/index/hashing.py`
    (`hash_file`/`classify_changes`), and `update_index` that re-parses/re-embeds only
    added/changed files, prunes deleted ones, and recomputes links.
  - Repo-relative id normalization (resolves Week-1 carry-over M1).
  - CLI: `build-index` is incremental-by-default with `--full` and `--no-embeddings`.
  - All embedding/linking/incremental logic tested via `FakeEmbedder` (offline); the real
    bge-small test is gated behind `DOCSMITH_RUN_MODEL_TESTS=1`. 110 tests passing.
- **Index Core (Week 1)** — the deterministic, zero-LLM foundation:
  - Core data models: `Symbol`, `DocSection`, `Link`, `Index` (`src/models.py`).
  - Language registry with tree-sitter symbol queries for Python, TypeScript, JavaScript,
    and Go (`src/parsing/languages.py`).
  - Code parser extracting functions/classes/methods (with Python docstrings) via
    tree-sitter (`src/parsing/code_parser.py`).
  - Markdown doc parser splitting by heading and extracting symbol/config-key references
    (`src/parsing/doc_parser.py`).
  - Deterministic symbol↔section linker by name (`src/index/linker.py`).
  - JSON index persistence with tuple-preserving round-trip (`src/index/store.py`).
  - Index builder that walks a repo, parses code + docs, links, and writes
    `.docsmith/index.json` (`src/index/builder.py`); disambiguates colliding ids.
  - `docsmith.py build-index` CLI subcommand.
  - 45 passing tests (unit + integration); fixture repo spanning four languages + markdown.
- Design spec for the self-healing documentation system
  (`docs/superpowers/specs/2026-06-11-self-healing-docs-design.md`).
- Forge-inspired repository scaffolding: `src/` (parsing, index, detection, repair,
  github, llm, utils), `tests/`, `evaluation/`, `configs/`, `scripts/`, `docs/`.
- Project tooling: `pyproject.toml`, `requirements.txt`, `Dockerfile`, `action.yml`,
  `.pre-commit-config.yaml`, `.env.example`, `.claude/CLAUDE.md`.
- GitHub Actions CI workflow (`ruff` + `pytest`).
- Week 1 implementation plan — Index Core
  (`docs/superpowers/plans/2026-06-11-index-core.md`).
- Living project docs: `docs/planning/roadmap.md` (progress tracker) and this changelog.
- CI smoke test verifying the `src` package imports.

### Changed
- CI now runs the full test suite (was unit-only) and opts into Node 24.
- Locked embeddings to a local model (`BAAI/bge-small-en-v1.5`) — free, no API key.
- Rewrote the Week 1 plan to describe interfaces/behavior/tests instead of embedding full
  implementation code (code is written during execution).

### Fixed
- `build_index` always resets the vector store on a clean build, preventing orphaned
  vectors (and resulting dangling embedding links) when a stale Chroma collection outlives
  its JSON index.
- Shortened over-length stub docstrings to satisfy `ruff` line-length (CI was red).
