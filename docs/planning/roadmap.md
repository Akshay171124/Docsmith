# Docsmith Roadmap & Progress

Living progress tracker for the project. The authoritative design is the
[design spec](../superpowers/specs/2026-06-11-self-healing-docs-design.md); detailed,
executable task plans live in [`docs/superpowers/plans/`](../superpowers/plans/). This
file is the human-facing rollup of *where we are*.

**Status legend:** ✅ done · 🚧 in progress · ⬜ not started

**Current focus:** Executing Week 1 — Index Core.

---

## Phase 0 — Project setup ✅
- ✅ Brainstormed scope; design spec written and approved
- ✅ Repo structure scaffolded (Forge-inspired layout)
- ✅ GitHub repo created and pushed (public)
- ✅ CI workflow (ruff + pytest) green
- ✅ Living docs established (this file + `CHANGELOG.md`)

## Week 1 — Index Core 🚧
Detailed plan: [2026-06-11-index-core.md](../superpowers/plans/2026-06-11-index-core.md).
Goal: parse a repo into code symbols + doc sections, link them by name, persist to
`.docsmith/index.json`. Pure/deterministic, zero LLM.

| Task | Description | Status |
|---|---|---|
| 0 | Pin tree-sitter deps + fixture repo | ⬜ |
| 1 | Core data models (`src/models.py`) | ⬜ |
| 2 | Language registry (`src/parsing/languages.py`) | ⬜ |
| 3 | Code parser — Python symbols + docstrings | ⬜ |
| 4 | Code parser — TS/JS/Go | ⬜ |
| 5 | Doc parser — split into sections | ⬜ |
| 6 | Doc parser — reference extraction | ⬜ |
| 7 | Deterministic linker (`src/index/linker.py`) | ⬜ |
| 8 | Index store — JSON round-trip | ⬜ |
| 9 | Index builder — walk repo → parse → link | ⬜ |
| 10 | `build-index` CLI subcommand | ⬜ |

## Week 2 — Retrieval layer ⬜
Local embeddings (bge-small) + Chroma, hybrid linking (symbol + embedding recall),
incremental index updates, API-reference + config/CLI/env extractors.

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
