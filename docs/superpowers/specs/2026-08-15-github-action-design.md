# GitHub Action (Week 5) — Design Spec

**Date:** 2026-08-15
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** Repair Engine (Week 4) + LLM Staleness Investigator + Detection Core (Week 3)
+ Retrieval Core (Week 2) + Index Core (Week 1)

---

## 1. Goal & Scope

Turn the repair engine's `RepairResult` into **real GitHub output on a pull request**: an
always-posted **summary comment**, AUTOFIX corrections collected into **one companion
fix-PR**, and FLAG items rendered in the summary with proposed diffs. This is stage 9 of the
original pipeline and the project's first live-GitHub integration.

**In scope:**
- A `GitHubClient` seam (the write side: summary comment + companion fix-PR), with a real
  `PyGithubClient` and a `FakeGitHubClient` for offline tests.
- A PR-context loader that reads the Actions event payload + environment.
- A Reporter that builds the summary comment, applies AUTOFIX corrections to doc files, and
  opens/updates the companion fix-PR.
- The `docsmith --github-action` entrypoint wiring inputs → settings → index → `repair_pr`
  → Reporter → Action outputs.
- Finalizing `action.yml` and `Dockerfile`.

**Out of scope (Week 6):** the evaluation / history-replay harness, metrics report, README
numbers, demo video.

**Non-goals:** **Never auto-merges** — a human always approves. No required paid API usage:
the default test suite is **$0/offline** (fake GitHub + fake LLM), and the Action runs live
at **$0** on free local Ollama + the free `github.token`. Flipping to Claude later is one
input, no code change.

---

## 2. Cost posture (a hard requirement, carried over)

- **Tests** use `FakeGitHubClient` + `FakeLLMClient` — no network, no token, no key, **$0**,
  in CI on every commit.
- **The live Action** runs on `OllamaClient` (default) + the free `github.token` — **$0**.
  The real end-to-end demo runs on a **self-hosted runner** (the user's Mac, where Ollama is
  reachable) or by running the same entrypoint locally against a real test PR.
- **Claude** is opt-in: set `llm-backend: claude` + provide `anthropic-api-key`. Never the
  default, never required, never invoked by the default suite.

Importing any module must never require `github` (PyGithub), `anthropic`, a network call, or
a token/key — the real clients lazy-import their SDK inside methods (mirroring
`BgeSmallEmbedder`/`ClaudeClient`).

---

## 3. Architecture & data flow

```
Action runner (repo checked out via actions/checkout at base..head)
   │  load_pr_context(env, event JSON) → PRContext(repo, base_sha, head_sha, pr_number, head_ref, base_ref)
   │  build/refresh index on the head checkout
   ▼
repair_pr(repo_root, base_sha, head_sha, index_path, settings, llm_client)   (Week 4, +verified count)
   │      → RepairResult(outcomes, skipped, verified)
   ▼  report(result, pr_context, settings, gh_client) → ReportCounts(verified, fixed, flagged)
      · build summary markdown (headline counts + AUTOFIX list w/ fix-PR link + FLAG diffs)
      · apply each AUTOFIX revised_text into its doc file (span-replace via index sections)
      · open/update ONE companion fix-PR with those file edits   (iff auto_fix and ≥1 AUTOFIX)
      · upsert the summary comment (idempotent via a hidden marker)
   ▼
write outputs verified / fixed / flagged / fix-pr-url  → $GITHUB_OUTPUT
```

Detection reads the diff via local `git` on the checkout (Week 3 `run_detection`), so the
`GitHubClient` needs no diff-fetch API — it is purely the write side.

---

## 4. Components

### 4.1 PR context (`src/github/context.py`)
- `PRContext` (frozen): `repo: str` (`"owner/name"`), `base_sha: str`, `head_sha: str`,
  `pr_number: int`, `head_ref: str`, `base_ref: str`.
- `load_pr_context(env: Mapping[str, str]) -> PRContext` — reads `GITHUB_REPOSITORY` and the
  `pull_request` event JSON at `env["GITHUB_EVENT_PATH"]` (`pull_request.base.sha`,
  `pull_request.head.sha`, `pull_request.head.ref`, `pull_request.base.ref`, `number`). Pure
  over its inputs; unit-tested with a fixture event JSON. Raises a clear error if the event
  is not a `pull_request` payload.

### 4.2 `GitHubClient` seam (`src/github/client.py`)
- Protocol (`@runtime_checkable`), the write side only:
  - `upsert_summary_comment(pr_number: int, body: str) -> None` — find an existing issue
    comment containing the hidden marker `<!-- docsmith:summary -->` → edit it; else create a
    new one. Idempotent across re-runs.
  - `open_or_update_fix_pr(head_ref: str, base_ref: str, branch: str, files: dict[str, str],
    title: str, body: str) -> str` — create or force-update `branch` off `head_ref`, commit
    the `{path: new_content}` file changes to it, open a PR (`branch` → `base_ref`) or update
    the existing one's body; returns the PR URL.
- `PyGithubClient(repo: str, token: str)` — the real implementation; **lazy-imports
  `github`** inside its methods so importing the module needs no SDK/token/network. Uses the
  PyGithub contents API to read/create/update files on the branch and the issues/pulls API
  for comments and PRs.
- `FakeGitHubClient` — records every call (upserted comment bodies keyed by `pr_number`;
  fix-PR calls with their file maps) and returns a canned PR URL. Deterministic, offline.
  Lets tests assert exactly what *would* be posted/opened. A test double, not a mock of the
  product.

### 4.3 Reporter (`src/github/reporter.py`)
- `report(result: RepairResult, pr_context: PRContext, settings: Settings,
  client: GitHubClient, index: Index, read_file: Callable[[str], str]) -> ReportCounts`.
  The `index` supplies section line spans; `read_file(path) -> str` reads a doc file's
  current content (the entrypoint injects one that reads from the checkout; tests inject a
  fixture reader). Both injected so the Reporter is unit-tested without disk or GitHub.
- `ReportCounts` (frozen): `verified: int`, `fixed: int`, `flagged: int`, `fix_pr_url: str | None`.
- Behavior:
  1. Partition `result.outcomes` by route: AUTOFIX, FLAG (NO_CHANGE is ignored in output but
     not counted as verified).
  2. **AUTOFIX application (deterministic):** for each AUTOFIX outcome, read the doc file's
     current content, replace the section's lines (`DocSection.start_line..end_line`, resolved
     from the index passed in — see §4.4) with `proposal.revised_text`, producing a
     `{path: new_content}` map. Multiple AUTOFIX edits to the same file are applied together
     (bottom-up by line so earlier edits don't shift later line numbers).
  3. **Companion fix-PR:** iff `settings.auto_fix` and the AUTOFIX map is non-empty, call
     `open_or_update_fix_pr(head_ref, base_ref, branch=f"docsmith/fix-pr-{pr_number}", files,
     title, body)`; capture the URL. When `auto_fix` is false, open no PR (AUTOFIX items are
     still listed in the summary as "proposed").
  4. **Summary comment (always):** build the markdown (see §4.5) and
     `upsert_summary_comment(pr_number, body)`.
  5. Return `ReportCounts(verified=result.verified, fixed=len(autofix), flagged=len(flag),
     fix_pr_url=...)`.
- The Reporter receives the loaded `Index` (for section line spans) alongside the result —
  the entrypoint loads it once and passes it in.

### 4.4 AUTOFIX file application (`src/github/apply.py`)
- `apply_corrections(outcomes: list[RepairOutcome], index: Index, read_file) -> dict[str, str]`
  — pure over an injected `read_file(path) -> str` (so it is unit-tested without disk/GitHub).
  Groups AUTOFIX outcomes by file, sorts each file's edits by descending `start_line`, and
  splices `revised_text` into `lines[start_line-1:end_line]`. Returns the new full content per
  changed file. Section spans come from `index.sections[section_id]`.

### 4.5 Summary markdown (`src/github/summary.py`)
- `build_summary(result: RepairResult, fix_pr_url: str | None, auto_fix: bool) -> str`.
- Layout: a hidden marker line `<!-- docsmith:summary -->`; a headline
  `**Docsmith:** {verified} verified · {fixed} auto-fixed{ (PR link) } · {flagged} flagged`;
  an **Auto-fixed** section listing each AUTOFIX `file#section` (linking the fix-PR); a
  **Needs review** section where each FLAG item shows `file#section`, the diagnosis
  (`reason`), and the proposed correction inside a collapsible `<details><summary>…</summary>`
  fenced diff block (`proposal.diff`). Skipped-count footnote when non-empty. Never mentions
  merging.

### 4.6 Action entrypoint (`docsmith.py`, `--github-action`)
- Reads Actions env: `INPUT_LLM-BACKEND`, `INPUT_OLLAMA-HOST`, `INPUT_CONFIDENCE-THRESHOLD`,
  `INPUT_DOC-GLOBS`, `INPUT_IGNORE-GLOBS`, `INPUT_AUTO-FIX`, `INPUT_ANTHROPIC-API-KEY`,
  `GITHUB_TOKEN`/`INPUT_GITHUB-TOKEN`, plus the `GITHUB_*` context.
- Steps: merge inputs into `Settings` (backend, ollama host, threshold, doc globs, auto_fix);
  `load_pr_context(os.environ)`; build/refresh the index on the checkout
  (`build_index(repo, output_path, embeddings=True)`); `client = make_client(settings)`;
  `result = repair_pr(repo, base_sha, head_sha, index_path, settings, client)`;
  `gh = PyGithubClient(pr_context.repo, token)`; `counts = report(result, pr_context,
  settings, gh, index, read_file)` where `read_file` reads from the checkout
  (`lambda p: (Path(repo_root) / p).read_text()`); write
  `verified`/`fixed`/`flagged`/`fix-pr-url` to `$GITHUB_OUTPUT`.
- A backend-unavailable or GitHub API error surfaces clearly and exits non-zero (fails the
  Action step) — consistent with the established `RuntimeError`-propagation rule.

### 4.7 `RepairResult.verified` (small Week-4 addition, `src/detection/models.py` + `engine.py`)
- Add `verified: int = 0` to `RepairResult` (additive — the Week-4 `docsmith repair` CLI is
  unaffected). `repair_pr` sets it to the number of investigator verdicts that were **not**
  stale (sections confirmed accurate). The `docsmith repair` CLI may show it too.

---

## 5. Packaging

### 5.1 `action.yml`
- Make `anthropic-api-key` **optional** (`required: false`, no default).
- Add `llm-backend` (default `ollama`) and `ollama-host` (default
  `http://host.docker.internal:11434`, so the container reaches the host's Ollama on a
  self-hosted runner).
- Keep `github-token` (default `${{ github.token }}`), `confidence-threshold`, `doc-globs`,
  `ignore-globs`, `auto-fix`.
- Outputs: `verified`, `fixed`, `flagged`, and `fix-pr-url`.

### 5.2 `Dockerfile`
- Replace the model-warm TODO with a real pre-download of `BAAI/bge-small-en-v1.5` into an
  image layer (so the Action needs no embedding download at runtime). Keep `git` installed;
  entrypoint stays `python /app/docsmith.py --github-action`.

---

## 6. Error handling & idempotency

- **Re-runs** (every push to the PR) **update** the same summary comment (found by the hidden
  marker) and **reuse** the deterministic fix branch `docsmith/fix-pr-{pr_number}` — never
  duplicating comments or PRs.
- **AUTOFIX span-replace** trusts the index's section spans; if a section is missing from the
  index (edge case), that outcome is skipped from the fix-PR and noted, never crashing the
  run.
- Backend-unavailable (Ollama down / missing Claude key) and GitHub API failures are raised
  and fail the Action step with a clear message — never silently swallowed.

---

## 7. Testing ($0/offline)

- **Unit:**
  - `load_pr_context` — a fixture `pull_request` event JSON → correct `PRContext`; a
    non-PR event → clear error.
  - `apply_corrections` — AUTOFIX outcomes + a fixture index + injected `read_file` → correct
    new file content; multiple edits to one file applied bottom-up without line drift.
  - `build_summary` — asserts the marker, headline counts, the AUTOFIX list, and the FLAG
    `<details>` diff blocks (exact-substring); `auto_fix=false` still lists AUTOFIX as
    proposed.
  - Reporter with `FakeGitHubClient` — one upserted comment + (when `auto_fix`) one fix-PR
    with the right `{path: content}`; `auto_fix=false` → no PR; a second `report(...)` call
    updates rather than duplicates (asserted via the fake's recorded calls).
  - `PyGithubClient` with the `github` SDK boundary **mocked** — asserts it looks up the
    marker comment and edits vs. creates, and force-updates the branch + opens/updates the PR.
    (No real token.)
- **Integration (all fakes):** full `--github-action` path on a temp git repo (base commit +
  head commit changing a documented symbol) with `FakeLLMClient` (scripted stale→rewrite→
  validate) + `FakeGitHubClient` → asserts the summary body, the fix-PR file contents, and the
  written output counts. Runs in CI, **$0**.
- **Gated real-GitHub test (manual/local, not CI):** the real path against a throwaway test
  repo, skipped unless `DOCSMITH_RUN_GITHUB_TESTS=1` and a token is present. The **"run on a
  real fork"** demo is the manual DoD.

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| GitHub-hosted runners can't run Ollama; no paid budget | Backend-configurable, key optional; the live demo runs on a self-hosted runner (Mac + Ollama) or a local entrypoint run, both $0; CI uses fakes. |
| Duplicate comments/PRs on every push | Idempotent: marker-based comment upsert + a deterministic reused fix branch. |
| Inline review comments can't attach to unchanged doc files | FLAG items render in the summary comment with collapsible proposed diffs (decided in brainstorming), not as inline review comments. |
| AUTOFIX line-number drift when multiple edits hit one file | Apply a file's edits bottom-up (descending `start_line`). |
| Importing the module pulls PyGithub/anthropic | Both real clients lazy-import their SDK inside methods; a unit test asserts neither is imported at module load. |
| Index staleness relative to the PR head | Build/refresh the index on the head checkout each run (accepted cost; Week 6 may optimize). |

---

## 9. Definition of Done

- On a real pull request, the Action posts a summary comment, opens **one** companion fix-PR
  for AUTOFIX corrections (when `auto-fix` is on), and lists FLAG items with proposed diffs —
  running at **$0** on Ollama + `github.token`, and **never auto-merging**.
- `GitHubClient` seam with `PyGithubClient` + `FakeGitHubClient`; importing modules needs no
  SDK/token/network.
- Re-runs update the same comment and fix-PR rather than duplicating.
- `action.yml` makes the Claude key optional and adds `llm-backend`/`ollama-host`; the
  `Dockerfile` bakes in the embedding model.
- Default `pytest` suite fully offline ($0) and green; `ruff check .` clean.
- The gated real-GitHub test exists; the "run on a real fork" demo is documented.
