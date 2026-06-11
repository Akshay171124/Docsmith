# Docsmith

> A language-agnostic GitHub Action that keeps technical documentation in sync with code.

On every pull request, Docsmith detects which documentation the code changes have made
inaccurate, verifies the staleness with an LLM, and either opens a **companion fix-PR**
(high confidence) or **flags the section inline** for human review (low confidence) —
always posting a clear summary comment. It never auto-merges; a human always approves.

## How it works

```
PR ─► Diff Parser ─► Symbol Mapper ─► Candidate Linker ─► Triage Filter
                          (deterministic, no LLM)              │
                                                               ▼
                              Staleness Investigator (LLM + read/grep tools)
                                                               │
                                                               ▼
                          Repair ─► Validate ─► Confidence Router ─► GitHub Reporter
```

Stages 1–4 are deterministic (fast, free, explainable). The LLM enters only once
candidates are narrowed to genuine suspects.

| Layer | What it does |
|---|---|
| **Parsing** | tree-sitter symbol extraction (40+ languages) + doc/section parsing |
| **Index** | persisted, incrementally-updated code↔docs map with local embeddings (ChromaDB) |
| **Detection** | diff → changed symbols → suspect doc sections → LLM staleness verdict |
| **Repair** | rewrite stale spans → independent validation → confidence routing |
| **GitHub** | summary comment, companion fix-PRs, inline flags |

## Documentation sources covered

Markdown/README · in-code docstrings & JSDoc · API reference (OpenAPI/routes) ·
config/CLI/env-var docs.

## Quick start

```yaml
# .github/workflows/docsmith.yml
- uses: <owner>/docsmith@v1
  with:
    anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
    confidence-threshold: 0.8
```

## Local usage

```bash
pip install -r requirements.txt
python docsmith.py --repo . --base main --head HEAD
```

## Status

Early development. See [docs/superpowers/specs/2026-06-11-self-healing-docs-design.md](docs/superpowers/specs/2026-06-11-self-healing-docs-design.md)
for the design spec and [Todo.md](Todo.md) for the roadmap.
