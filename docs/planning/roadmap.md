# Docsmith Roadmap & Progress

Living progress tracker for the project. The authoritative design is the
[design spec](../superpowers/specs/2026-06-11-self-healing-docs-design.md); detailed,
executable task plans live in [`docs/superpowers/plans/`](../superpowers/plans/). This
file is the human-facing rollup of *where we are*.

**Status legend:** ✅ done · 🚧 in progress · ⬜ not started

**Current focus:** Weeks 1–2 complete ✅ — next up is Week 3 (Detection). Pending sub-project: the API-reference + config/CLI/env doc extractors deferred from Week 2.

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

## Week 3 — Detection ⬜
Diff parsing, symbol mapping for changed spans, triage filter, LLM staleness
investigator with read/grep tools.

## Week 4 — Repair ⬜
Targeted repair, validation pass, confidence router; structured outputs end-to-end.

## Week 5 — GitHub Action ⬜
Dockerfile + `action.yml` finalize, PR/comment/inline-flag workflow, run on a real fork.

## Week 6 — Evaluation & polish ⬜
History-replay harness, curated regression suite, metrics report + README numbers, demo
video, (stretch) Marketplace publish.
