# Self-Healing Technical Documentation — Design Spec

**Date:** 2026-06-11
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Working name:** Docwright (alternatives: Parity, Veritas)

---

## 1. Problem & Goal

Technical documentation drifts out of sync with code on every team. A function is
renamed, a config default changes, an endpoint gains a parameter — and the docs that
describe them silently become wrong. Nobody owns catching this, so docs rot until a
user hits the discrepancy.

**Goal:** A language-agnostic GitHub Action that runs on every pull request, detects
which documentation the code changes have made inaccurate, verifies the staleness with
an LLM, and either (a) opens a companion PR with the corrected docs when confidence is
high, or (b) flags the stale section inline for human review when it is not — always
posting a clear summary comment.

**Non-goals:**
- No auto-merging of generated doc changes — a human always approves.
- Not a general doc *generator* (it repairs existing docs; it does not author new docs
  from scratch for undocumented code).
- Not a prose style linter.

---

## 2. Key Decisions (locked during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Target codebases | **Language-agnostic** via tree-sitter | "Anyone can install it"; one parsing toolchain for 40+ languages. |
| Detection/repair architecture | **Hybrid**: deterministic pipeline + LLM investigator | Cheap/explainable where possible; LLM judgment only where needed. |
| Doc↔code linking | **Hybrid**: symbol-match (precision) + embeddings (recall) | Anchored in explainable matching; embeddings recover unnamed references. |
| Doc sources | Markdown/README, docstrings/JSDoc, API reference (OpenAPI/routes), config/CLI/env docs | All four; they reinforce each other. |
| Output behavior | **Confidence-tiered, no auto-merge** | Companion PR for high-confidence fixes; inline flag for low; summary always. |
| LLM | **Claude Sonnet** | Strong code understanding for verify/repair/validate. |
| Index | **Persisted + incrementally updated**, stored in-repo | Avoid re-embedding the whole repo per PR; versioned and reviewable. |
| Embeddings | **Local model** (`BAAI/bge-small-en-v1.5` via sentence-transformers) | Free, no extra API key, self-contained Action. |
| Evaluation | **Git-history replay (headline) + curated CI suite** | Real-world ground truth; rigorous, credible README numbers. |
| Implementation language | **Python 3.11+** | Best ergonomics for tree-sitter, ChromaDB, PyGithub. |

---

## 3. Architecture

```
                    ┌─────────────────── INDEX (persisted, incremental) ───────────────────┐
                    │   code symbols (tree-sitter)  ·  doc sections  ·  symbol↔doc links    │
                    │   embeddings (code + docs)    ·  stored as JSON + Chroma on disk      │
                    └───────────────────────────────────▲──────────────────────────────────┘
                                                         │ query / update
  PR event ──► [1 Diff Parser] ──► [2 Symbol Mapper] ──► [3 Candidate Linker] ──► [4 Triage Filter]
              changed files/lines    diff → code units      symbols+embeddings        drop trivial
                                      (tree-sitter)          → suspect doc sections    changes
                                                                       │
                                                                       ▼
                              ┌──────────── DETERMINISTIC ══╪══ LLM ────────────────────┐
                              │   [5 Staleness Investigator] (LLM + tools: read/grep)   │
                              │      old code + new code + doc section → stale? why?    │
                              └──────────────────────────┬──────────────────────────────┘
                                                         ▼
                              [6 Repair Engine] ─► [7 Validator] ─► [8 Confidence Router]
                              rewrite stale parts   2nd LLM checks    high → fix-PR
                              preserve style        accuracy+style    low  → inline flag
                                                                       │
                                                                       ▼
                                              [9 GitHub Reporter] — summary comment, PRs, flags
```

**The deterministic/LLM boundary is a core design principle.** Stages 1–4 use no LLM:
they are fast, free, deterministic, and unit-testable without mocking a model. The LLM
enters only at stage 5, after candidates are narrowed to genuine suspects, which keeps
cost and latency bounded.

---

## 4. Components

Each component has one purpose and a defined interface so it can be tested in isolation.

### 4.1 Index Builder & Store
- **Purpose:** Build and maintain the code↔docs index.
- **Inputs:** repo root (full build) or changed file list (incremental update).
- **Outputs:** persisted index (JSON for symbols/sections/links; Chroma collection for
  embeddings), stored in-repo (e.g. `.docwright/`).
- **Index contents:**
  - **Code symbols:** `{id: "path::Class.method", kind, signature, docstring, span, language}`
  - **Doc sections:** `{id: "file#heading-path", raw, referenced_symbols[], referenced_config_keys[]}`
  - **Links:** symbol↔section edges, each `{via: symbol-match | embedding | both, score}`
  - **Embeddings:** code + doc vectors in a file-based Chroma collection.
- **Incremental update:** only re-parse / re-embed files in the changed set; prune
  symbols/sections for deleted files.

### 4.2 Diff Parser (stage 1)
- **Purpose:** Turn a PR into changed files and hunks.
- **Inputs:** PR ref / base & head SHAs (from GitHub Actions context).
- **Outputs:** list of `{file, hunks:[{old_span, new_span, added, removed}]}`.

### 4.3 Symbol Mapper (stage 2)
- **Purpose:** Map changed line spans to the code symbols they touch, before & after.
- **Inputs:** changed hunks + old/new file contents.
- **Outputs:** `{symbol_id, old_signature, new_signature, change_kind}` pairs
  (added / removed / signature-changed / body-changed).
- **Tooling:** tree-sitter per language.

### 4.4 Candidate Linker (stage 3)
- **Purpose:** For each changed symbol, find doc sections that might describe it.
- **Inputs:** changed symbols + index.
- **Outputs:** suspect `(symbol, doc_section, link_evidence)` tuples.
- **Logic:** symbol-name match first (precise); embedding similarity above threshold for
  recall (catches docs describing behavior without naming the symbol).

### 4.5 Triage Filter (stage 4)
- **Purpose:** Deterministically drop changes that cannot affect docs.
- **Drops:** whitespace/comment-only, test files, pure-internal refactors with unchanged
  public signatures. Configurable via globs/rules.
- **Outputs:** surviving suspect tuples.

### 4.6 Staleness Investigator (stage 5, LLM + tools)
- **Purpose:** Decide whether each suspect doc section is actually stale.
- **Inputs:** old code, new code, doc section content; tools `read_file`, `grep`.
- **Outputs (structured):** `{stale: bool, confidence, diagnosis, affected_spans[]}`.
- **Why tools:** a renamed parameter may be referenced in files outside the diff; the
  investigator can confirm true blast radius rather than infer from the diff alone.
- **Role:** false-positive filter — only confirmed-stale sections proceed.

### 4.7 Repair Engine (stage 6, LLM)
- **Purpose:** Rewrite only the stale spans of a confirmed section.
- **Inputs:** current section, new code, staleness diagnosis.
- **Outputs:** revised section text + a list of changed spans.
- **Constraint:** preserve tone/structure; explicit instruction to leave correct parts
  untouched.

### 4.8 Validator (stage 7, LLM)
- **Purpose:** Quality gate before anything reaches GitHub.
- **Checks:** does the rewrite match the new code? were correct parts preserved? is style
  consistent? 
- **Outputs (structured):** `{accurate: bool, preserved: bool, style_ok: bool, notes}`.

### 4.9 Confidence Router (stage 8)
- **Purpose:** Decide fix-PR vs. inline flag.
- **High confidence** (→ companion fix-PR): mechanical changes (renamed param, changed
  default, added/removed config key) that pass validation cleanly.
- **Low confidence** (→ inline flag with TODO draft): new features, removed capabilities,
  or anything the validator flags.

### 4.10 GitHub Reporter (stage 9)
- **Purpose:** Communicate results.
- **Always:** one summary comment, e.g. *"Doc Check: 3 verified accurate · 1 auto-fixed
  (PR #42) · 2 flagged for review."*
- **High confidence:** create branch, apply correction, open companion PR linked from the
  comment.
- **Low confidence:** inline flag on the triggering PR with diagnosis + TODO draft.
- **Never auto-merges.**

---

## 5. GitHub Action Packaging

- **Form:** Docker action + `action.yml`.
- **Inputs:** LLM API key, confidence threshold, doc globs, ignore globs, auto-fix on/off.
- **Outputs:** counts of verified / auto-fixed / flagged sections; links to created PRs.
- **Trigger:** `pull_request` on changes to code files.

---

## 6. Evaluation

### 6.1 History replay (headline benchmark)
Mine commits that changed **both** code and docs together. The doc edit is ground truth
for what *should* change. Hide the doc edit, feed our tool the code diff, and measure
whether it reproduces the correct fix. Metrics: TP / FP / FN for detection, plus
correction-quality scoring (exact/semantic match against the real doc edit).

### 6.2 Curated CI suite (regression)
Hand-labeled should/shouldn't-update cases on a forked, well-documented repo
(e.g. FastAPI, Pydantic). Runs in CI to catch regressions. Tracks the same metrics.

### 6.3 Reporting
Headline numbers published in the README.

---

## 7. Tech Stack

| Component | Choice |
|---|---|
| Language | Python 3.11+ |
| Parsing | tree-sitter (multi-language symbol extraction) |
| Embeddings | Local: `BAAI/bge-small-en-v1.5` via `sentence-transformers` (free, no API key) |
| Vector store | ChromaDB (file-based) |
| LLM | Claude Sonnet (verify, repair, validate) |
| Git / CI | PyGithub + GitHub Actions |
| Containerization | Docker |

---

## 8. Milestones (~6 weeks)

1. **Wk 1 — Index core:** tree-sitter symbol extraction (3–4 languages), markdown +
   docstring parsing, deterministic linking, JSON index.
2. **Wk 2 — Retrieval layer:** embeddings + Chroma, hybrid linking, incremental update;
   API-reference + config/CLI extractors.
3. **Wk 3 — Detection:** diff parsing, symbol mapping, triage filter, LLM staleness
   investigator with tools.
4. **Wk 4 — Repair:** repair + validator + confidence router; structured outputs
   end-to-end.
5. **Wk 5 — Action:** Dockerize, `action.yml`, PR/comment/flag workflow, run on a real
   fork.
6. **Wk 6 — Evaluation & polish:** history-replay harness + curated suite, README with
   metrics, demo video, optional marketplace publish.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Embedding links too noisy | Symbol-match is primary; embeddings are recall-only and threshold-tuned; all links carry evidence tags for debugging. |
| LLM false positives flagging accurate docs | Stage-5 investigator is a dedicated filter; stage-7 validator is a second gate; confidence routing keeps risky fixes out of auto-PRs. |
| Multi-language scope creep | Start with 3–4 languages in Wk 1; add more only if time allows. Tree-sitter makes each addition incremental. |
| Cross-file blast radius missed | Investigator has `read_file`/`grep` tools to verify usage beyond the diff. |
| LLM cost/latency in CI | Deterministic stages 1–4 narrow candidates before any LLM call; index avoids re-embedding. |
| History-replay ground truth is noisy (docs and code changed for unrelated reasons in same commit) | Filter to commits with tight code+doc coupling; supplement with curated cases. |

---

## 10. Changes vs. Original Brief

- **tree-sitter** replaces single-language parsing → truly language-agnostic.
- **Hybrid linking** (symbols-first, embeddings for recall) replaces embeddings-first →
  more precise while keeping the retrieval stack.
- **LLM investigator with tools** replaces a blind single-prompt verify → catches
  cross-file blast radius.
- **History-replay evaluation** replaces "deliberately break things" → rigorous, real
  ground truth (curated cases retained for regression).
- All other original elements retained: confidence tiers, companion PRs, summary comment,
  Docker action, marketplace publish (stretch).
