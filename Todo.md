# Docsmith Roadmap

> **All six milestones are complete.** This file is kept as a historical pointer; the
> authoritative, per-task progress tracker is
> [`docs/planning/roadmap.md`](docs/planning/roadmap.md).

Milestones mirrored the design spec
(`docs/superpowers/specs/2026-06-11-self-healing-docs-design.md`):

- [x] **Week 1 — Index core** — tree-sitter symbols + doc sections, deterministic linking, JSON index
- [x] **Week 2 — Retrieval layer** — local embeddings (Chroma), hybrid linking, incremental updates
- [x] **Week 3 — Detection** — diff → symbol mapping → triage → candidate linking
- [x] **LLM Staleness Investigator** — single-prompt structured verdicts behind a pluggable client seam
- [x] **Week 4 — Repair** — targeted repair, validation pass, confidence router
- [x] **Week 5 — Action** — Dockerfile + `action.yml`, PR/comment/fix-PR workflow
- [x] **Week 6 — Evaluation & polish** — curated corpus + history-replay harness, metrics report

**Not built (optional / stretch):** the API-reference + config/CLI/env doc extractors
(deferred from Week 2), a demo video, and (stretch) Marketplace publish.
