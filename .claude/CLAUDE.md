# Claude Rules for Docsmith

## Communication Style
- Be concise. Short answers are preferred over verbose explanations.
- Don't ask unnecessary clarifying questions — make reasonable decisions.
- When the user provides feedback or a preference, apply it without lengthy justification.
- "clear" means acknowledged, move on.
- **Voice tradeoffs**: When a request has meaningful downsides, flag them concisely before proceeding. If the user still wants to go ahead, proceed without hesitation.

## Project Context
Docsmith is a **language-agnostic GitHub Action** that keeps technical documentation in
sync with code. On each PR it detects stale docs, verifies with an LLM, and either opens
a companion fix-PR (high confidence) or flags inline (low confidence). **It never auto-merges.**

- **Design spec (source of truth):** `docs/superpowers/specs/2026-06-11-self-healing-docs-design.md`
- **Roadmap:** `Todo.md`
- Entry point: `docsmith.py` (runs both locally and inside the Action).
- Config in `configs/` uses layered YAML (`base.yaml` + overrides + action inputs).

## Architecture (the deterministic/LLM boundary is load-bearing)
Stages 1–4 are deterministic and unit-testable without an LLM. The LLM enters only at
stage 5, after candidates are narrowed — this keeps cost, latency, and flakiness down.

| Layer (`src/`) | Responsibility |
|---|---|
| `parsing/` | tree-sitter code symbols + doc/section parsing |
| `index/` | persisted, incremental code↔docs map + local embeddings (Chroma) |
| `detection/` | diff → symbols → candidate links → triage → LLM staleness verdict |
| `repair/` | rewrite stale spans → validate → confidence routing |
| `github/` | diff fetch, summary comment, companion PRs, inline flags |
| `llm/` | Claude client, agent tools (read_file/grep), prompts |
| `utils/` | layered config, logging |

## Locked Decisions
- **Language-agnostic** via tree-sitter (not single-language).
- **Hybrid linking**: symbol-name match (precision) + embeddings (recall).
- **LLM**: Claude Sonnet.
- **Embeddings**: local `BAAI/bge-small-en-v1.5` (free, no API key, baked into the image).
- **Index**: persisted in-repo (`.docsmith/`), updated incrementally per PR.
- **Output**: confidence-tiered, **never auto-merge** — a human always approves.
- **Evaluation**: git-history replay (headline) + curated CI suite.

## Code Style
- Include docstrings for functions with Args/Returns sections.
- Use descriptive variable names; prefer general over overly specific naming.
- Add comments only where logic isn't self-evident.
- **Defensive programming**: make the safe behavior the default. Enforce invariants in one
  place rather than relying on every call site to remember them.

## Testing
- **TDD (non-negotiable)**: for ALL new Python functions and behavior changes, write a
  failing test first, then implement. This includes utility functions, not just bug fixes.
- Tests in `tests/` mirror `src/`: `tests/unit/` for units, `tests/integration/` for E2E.
- The deterministic pipeline (stages 1–4) must be fully testable with fixtures and no LLM
  calls. Mock the LLM at the `src/llm/client.py` boundary for stages 5–7.
- Use `tests/fixtures/` for sample repos, diffs, and doc sections.

## Git Workflow
- Commit messages: short summary line, optional body for context.
- Do NOT mention LLM assistance anywhere (commits, PRs, code comments, docs) unless
  explicitly requested. No `Co-Authored-By`, "Generated with", "AI-assisted", or similar.
- Push only when explicitly asked.
- **DCP**: when the user says "DCP", do: **D**ouble-check the code, **C**ommit, **P**ush.
- **Merging**: squash-and-merge branches into main.

## Python Environment
- Use a local virtualenv: `python3.11 -m venv .venv && source .venv/bin/activate`.
- Dependencies live in `requirements.txt`. Add new deps there, then `pip install -r requirements.txt`.
- For optional heavyweight deps, make them gracefully optional in code.

## Implementation Plans
- Plans in `docs/superpowers/plans/` describe the **plan**, not the implementation:
  task breakdown, files to touch, interfaces/signatures, the behavior/algorithm, the
  test cases to assert, and exact commands. Do NOT paste full implementation code into a
  plan — the actual code is written during execution and lives in `src/`/`tests/`.

## Dates
- The current year is 2026. Use this when writing dates in docs, logs, etc.
