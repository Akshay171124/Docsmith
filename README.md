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

Docsmith defaults to a **free local Ollama** model, so it runs at **$0** with no API key
(see [Run it on a real PR](#run-it-on-a-real-pr-free-local) for the self-hosted-runner setup):

```yaml
# .github/workflows/docsmith.yml
- uses: <owner>/docsmith@v1
  with:
    llm-backend: ollama          # default; free, local, no API key
    confidence-threshold: 0.8
```

To use Claude instead, set `llm-backend: claude` and provide
`anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}` — no code change.

## Local usage

The CLI is subcommand-based. Build an index once, then detect / investigate / repair a
git range (all default to the free Ollama backend):

```bash
pip install -r requirements.txt

python docsmith.py build-index --repo .                       # → .docsmith/index.json
python docsmith.py investigate --repo . --base main --head HEAD   # LLM staleness verdicts
python docsmith.py repair      --repo . --base main --head HEAD   # + proposed fixes, routed
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

This demo covers the staleness-judgment stage; the repair and GitHub-reporting stages are
also built — see [See it fix docs](#see-it-fix-docs-free-local) and
[Run it on a real PR](#run-it-on-a-real-pr-free-local) below.

### See it fix docs (free, local)

With Ollama running (`ollama pull qwen2.5-coder:7b`), propose real doc corrections
on the bundled fixture — no API key, $0:

```bash
make repair-demo
```

Docsmith rewrites the stale section, an independent LLM pass validates the rewrite,
and each fix is routed: **AUTOFIX** (clean, mechanical, high-confidence) or **FLAG**
(needs human review). This demo is read-only — it prints the proposed unified diff without
writing files or opening PRs; the [GitHub Action](#run-it-on-a-real-pr-free-local) does that
on a real pull request. The backend is pluggable — `fake` (offline tests), `ollama`
(default), or `claude` (optional, needs `ANTHROPIC_API_KEY`).

## Run it on a real PR (free, local)

Docsmith ships as a GitHub Action. Because it defaults to a **free local Ollama**
model, you can run it end-to-end at **$0** on a **self-hosted runner** (e.g. your Mac):

1. Install Ollama and pull the model: `ollama pull qwen2.5-coder:7b`.
2. Register your machine as a repository **self-hosted runner** (Settings → Actions →
   Runners).
3. Add a workflow that runs on pull requests:

   ```yaml
   name: Docsmith
   on: pull_request
   jobs:
     docs:
       runs-on: self-hosted
       steps:
         - uses: actions/checkout@v4
           with:
             fetch-depth: 0            # Docsmith needs base..head history
         - uses: ./                    # or your published action ref
           with:
             llm-backend: ollama
             ollama-host: http://localhost:11434
   ```

On each PR, Docsmith posts a **summary comment**, opens **one companion fix-PR** for
high-confidence corrections, and lists lower-confidence items for review. It **never
auto-merges**. To use Claude instead, set `llm-backend: claude` and provide
`anthropic-api-key` — no code change.

## Try it (web playground)

Beyond the CLI and GitHub Action, Docsmith ships a small **web playground** — paste a
public PR URL, get staleness verdicts and proposed fix diffs back in the browser.

**Local dev, $0:**

```bash
make api   # FastAPI backend on :8000, defaults to the local Ollama backend
make web   # Vite dev server on :5173
```

Open `http://localhost:5173`, paste a public GitHub PR URL, and submit — the UI calls
the backend and renders verdicts plus proposed diffs, no API key required.

**Public deploy:**

- **Frontend** (`frontend/`) deploys to **Vercel** — set `VITE_API_BASE` (see
  `frontend/.env.example`) in the Vercel project settings to the backend's URL.
- **Backend** deploys via `Dockerfile.web` to any free container tier (e.g. Hugging
  Face Spaces or Render) — set `CORS_ORIGINS` to the deployed Vercel origin. In the
  cloud deployment there's no local Ollama to call, so the visitor picks **Claude** and
  supplies their own Anthropic API key in the UI — no code change required.
- **Optional:** set `GITHUB_TOKEN` on the backend to raise the GitHub API rate limit used
  when looking up PR metadata (unauthenticated requests are limited to 60/hour per IP).

The playground is **read-only** (it never posts to GitHub) and supports **public
repos only**.

## Evaluation

Docsmith ships a **curated evaluation suite** — bundled base/head file pairs with
hand-labeled gold staleness/fix data — plus a **history-replay harness** that mines a
real repository's own coupled code+doc commits and replays them, scoring Docsmith's
detection (precision/recall/F1) and repair (exact-match rate, correction similarity)
against the same metrics. Both run entirely offline against a `fake` LLM in CI, and
against a free local **Ollama** model when reproduced by hand — never a paid API — so
evaluation runs are always $0.

Reproduce the curated run locally (needs Ollama, see [above](#see-it-work-free-local)):

```bash
make eval          # runs the curated suite via Ollama, writes evaluation/data/runs/curated.json
make eval-report   # renders the metrics table into the "Results" section below
```

The demo video and Marketplace publish are manual follow-ups, tracked separately from
this evaluation harness.

## Results

<!-- docsmith:results -->

_Run `make eval && make eval-report` to populate (free, local, on Ollama)._

## Status

**Feature-complete.** All six sub-projects (Index, Retrieval, Detection, LLM Staleness
Investigator, Repair, GitHub Action) plus the evaluation harness are built and merged — the
full pipeline runs end-to-end as a $0 GitHub Action. **279 tests passing offline.**

See [docs/superpowers/specs/2026-06-11-self-healing-docs-design.md](docs/superpowers/specs/2026-06-11-self-healing-docs-design.md)
for the original design spec and [docs/planning/roadmap.md](docs/planning/roadmap.md) for the
per-sub-project progress tracker. Remaining optional/stretch work: the API-reference +
config/CLI/env doc extractors (deferred from Week 2), a demo video, and Marketplace publish.
