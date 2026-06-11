# Docsmith Roadmap

Milestones mirror the design spec
(`docs/superpowers/specs/2026-06-11-self-healing-docs-design.md`). ~6 weeks.

## Week 1 — Index core
- [ ] tree-sitter symbol extraction for 3–4 languages (`src/parsing/code_parser.py`)
- [ ] markdown + docstring section parsing (`src/parsing/doc_parser.py`)
- [ ] deterministic symbol↔section linking
- [ ] persist/load JSON index (`src/index/store.py`)

## Week 2 — Retrieval layer
- [ ] local embeddings + Chroma collection (`src/index/embeddings.py`)
- [ ] hybrid linking (symbol-match + embedding recall)
- [ ] incremental index update for changed files
- [ ] API-reference + config/CLI/env extractors

## Week 3 — Detection
- [ ] diff parsing (`src/detection/diff_parser.py`)
- [ ] symbol mapping for changed spans (`src/detection/symbol_mapper.py`)
- [ ] triage filter (`src/detection/triage_filter.py`)
- [ ] LLM staleness investigator with read/grep tools (`src/detection/investigator.py`)

## Week 4 — Repair
- [ ] targeted repair (`src/repair/repairer.py`)
- [ ] validation pass (`src/repair/validator.py`)
- [ ] confidence router (`src/repair/confidence_router.py`)
- [ ] structured outputs end-to-end

## Week 5 — Action
- [ ] Dockerfile + `action.yml` finalize
- [ ] PR / comment / inline-flag workflow (`src/github/reporter.py`)
- [ ] run on a real forked repo

## Week 6 — Evaluation & polish
- [ ] history-replay harness (`evaluation/history_replay/`)
- [ ] curated regression suite (`evaluation/curated/`)
- [ ] metrics report + README numbers (`evaluation/report.py`)
- [ ] demo video
- [ ] (stretch) publish to GitHub Actions Marketplace
