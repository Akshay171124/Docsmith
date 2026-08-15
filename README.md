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

## See it work (free, local)

You can see Docsmith produce real staleness verdicts from a local LLM, at $0, with no
API key:

```bash
# 1. Install Ollama (https://ollama.com) and pull a coding model.
ollama pull qwen2.5-coder:7b

# 2. Run the end-to-end demo.
make investigate-demo
```

The demo builds an index over a small sample repo, makes a scripted signature change
to a documented function, and runs `docsmith investigate --backend ollama` against it —
printing the model's staleness verdict for the now-outdated doc section.

The investigator's LLM backend is pluggable (`--backend` / `llm.backend` in config):

- `fake` — a scripted, offline stand-in used by the test suite.
- `ollama` (default) — free, local, no API key; requires a running Ollama server.
- `claude` — optional, higher-quality backend; requires `ANTHROPIC_API_KEY`.

Note this stage only judges whether a doc section is stale — the repair/fix-PR stages
described above are still in development.

### See it fix docs (free, local)

With Ollama running (`ollama pull qwen2.5-coder:7b`), propose real doc corrections
on the bundled fixture — no API key, $0:

```bash
make repair-demo
```

Docsmith rewrites the stale section, an independent LLM pass validates the rewrite,
and each fix is routed: **AUTOFIX** (clean, mechanical, high-confidence) or **FLAG**
(needs human review). It prints the proposed unified diff; it never writes files or
opens PRs (that's the Week 5 GitHub Action). The backend is pluggable — `fake`
(offline tests), `ollama` (default), or `claude` (optional, needs `ANTHROPIC_API_KEY`).

## Status

Early development. See [docs/superpowers/specs/2026-06-11-self-healing-docs-design.md](docs/superpowers/specs/2026-06-11-self-healing-docs-design.md)
for the design spec and [Todo.md](Todo.md) for the roadmap.
