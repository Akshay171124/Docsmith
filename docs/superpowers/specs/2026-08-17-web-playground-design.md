# Web Playground — Design Spec

**Date:** 2026-08-17
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** the full pipeline (Weeks 1–6 + LLM Staleness Investigator), all merged to `main`.

---

## 1. Goal & Scope

An always-on, **$0-to-host** web playground for Docsmith. A visitor pastes a **public GitHub
pull-request URL**, picks an LLM backend, and Docsmith fetches the PR, detects stale
documentation, and shows per-section **staleness verdicts + proposed fix diffs** — entirely
**read-only** (it never posts to GitHub). The playground lets the author *visualize the
product* and adds a full-stack web dimension (JSON API + UI + deploy) on top of the existing
pipeline.

This reuses the Weeks 3–5 machinery (`run_detection` → `investigate` → `repair_pr`) behind
the `LLMClient` seam; the new code is a decoupled web layer — a Python JSON API plus a
separate JavaScript single-page app.

**Stack:** a **FastAPI + Pydantic** JSON API (async, auto OpenAPI/Swagger docs), Dockerized
for a free tier; and a **React + TypeScript + Vite** single-page app (**Tailwind CSS** +
**shadcn/ui** for styling, **TanStack Query** for API data-fetching) deployed to **Vercel**.
The two are decoupled and talk over CORS.

**In scope:** the FastAPI API (`POST /api/analyze`, `GET /healthz`, CORS), a PR-fetch
module, an analyze orchestration that shapes the pipeline output into JSON, the React SPA,
local dev for both, a split deploy (Vercel frontend / Docker backend), and offline tests
(backend + frontend).

**Out of scope (Option C — the real hosted GitHub App, later):** posting comments / opening
fix-PRs; private repos; visitor GitHub tokens; webhooks; persistence / accounts.

**Non-goals:** No new detection/repair logic (the playground only *invokes and displays* the
existing pipeline). No paid API required to build/test; no secret storage.

---

## 2. Cost & credential posture (a hard requirement)

- **The playground is $0 to host:** it is stateless — no database, no background workers, no
  persisted secrets — so it fits a free tier.
- **LLM backend is bring-your-own, via the existing seam.** A cloud-hosted backend cannot
  reach a visitor's `localhost` Ollama, so the two supported run modes are:
  - **Local** (author's machine): backend defaults to local **Ollama** → the author
    visualizes the product at **$0**.
  - **Public deploy** (free tier): the visitor selects **Claude** and supplies their **own**
    Anthropic key → **$0 for the host**; the key is used per-request and never stored.
- Credentials (`api_key`) are read from the request, passed straight to `make_client`, used
  for that request only, and **never logged or persisted**. Tests use the offline `fake`
  backend — no network, no key.

Importing the web modules must not require a network call or a key; the LLM SDK stays
lazily imported (the seam already guarantees this).

---

## 3. Architecture & data flow

```
React SPA (Vercel): pr_url + backend(ollama|claude) + credential
     │  fetch (TanStack Query) → CORS → POST {API_BASE}/api/analyze
     ▼
FastAPI backend (webapp/, Docker on a free tier):
  1. validate pr_url — public https://github.com/{owner}/{repo}/pull/{n} only
  2. fetch_pr(pr_url, workdir) → (repo_path, base_sha, head_sha)
        · GitHub REST API for the PR's base/head SHAs (+ fork head repo)   [stdlib urllib]
        · git clone the base repo into workdir; fetch the PR head sha
  3. build_index(repo_path, embeddings=False, full=True)         # symbol-match linking, fast
  4. client = make_client(settings, backend_override=backend)    # settings carry key/host/model
  5. result = repair_pr(repo_path, base_sha, head_sha, index_path, settings, client)
  6. shape result → AnalyzeResult JSON; cleanup workdir (finally)
     ▼
Browser renders: a summary line + one card per stale section
                 (route badge, confidence, reason, wrong-claims, collapsible unified diff)
```

The backend imports `src/` directly. Only step 2 (PR fetch) and step 6 (shaping) are new
logic; steps 3–5 are existing functions called unchanged.

---

## 4. Components

### 4.1 PR fetch (`webapp/prfetch.py`)
- `parse_pr_url(url: str) -> tuple[str, str, int]` — returns `(owner, repo, number)` for a
  valid `https://github.com/{owner}/{repo}/pull/{n}` URL; raises `ValueError` otherwise
  (strict allowlist — host must be `github.com`, path shape exact).
- `fetch_pr(pr_url: str, workdir: str, *, token: str | None = None) -> tuple[str, str, str]`
  — parse; call the GitHub REST API `GET /repos/{owner}/{repo}/pulls/{n}` (stdlib `urllib`;
  optional bearer `token` from a `GITHUB_TOKEN` env var only raises the rate limit) to read
  `base.sha`, `head.sha`, and the head repo's clone URL (fork-aware); `git clone` the base
  repo into `workdir/repo` and fetch the head sha into it; return
  `(repo_path, base_sha, head_sha)`. Uses `git` via `subprocess` (mirrors `git_adapter`).
  Raises a clear error if the PR/repo is missing, private (404), or too large (see §6).

### 4.2 Analyze service (`webapp/service.py`)
- `AnalyzeResult` (frozen dataclass): `summary: dict[str, int]`
  (`verified`, `auto_fixable`, `flagged`, `skipped`) and
  `results: list[SectionResult]`.
- `SectionResult` (frozen): `file: str`, `section_id: str`, `route: str`
  (`autofix`/`flag`), `confidence: float`, `reason: str`, `wrong_claims: list[str]`,
  `diff: str`.
- `analyze(pr_url, backend, *, api_key=None, ollama_host=None, model=None,
  embeddings=False) -> AnalyzeResult` — creates a `tempfile.TemporaryDirectory()`,
  `fetch_pr` → `build_index` → build a `Settings` carrying the backend/host/model →
  `make_client(settings, backend_override=backend)`, then runs the pipeline and shapes the
  output; the temp dir is removed in a `finally`.
- **Why two pipeline calls:** a `SectionResult` needs both the investigator's judgment
  (`confidence`, `reason`, `wrong_claims` — which live on the `Verdict`) and the repair
  engine's output (`route`, proposed `diff` — which live on the `RepairOutcome`).
  `RepairResult.outcomes` do **not** carry the verdict fields, so `analyze` calls
  **`investigate_pr(...)`** to get the `InvestigationResult` (verdicts) **and**
  **`repair_pr(...)`** to get the `RepairResult` (outcomes), then **joins** them per
  `(symbol_id, section_id)`. (This re-runs detection+investigation twice — the accepted cost
  of composing from the two public orchestrators, matching the evaluation runner's approach;
  fine for a playground on modest PRs.)
- **Shaping:** for each **stale** verdict (`v.stale`), emit a `SectionResult` with
  `file = section_id.rsplit("#", 1)[0]`, `section_id`, `confidence`/`reason`/`wrong_claims`
  from the verdict, and `route`/`diff` from the joined `RepairOutcome` when one exists
  (route = `outcome.route.value`, `diff = outcome.proposal.diff`); a stale verdict with no
  outcome (repair reply was skipped) gets `route="skipped"`, empty `diff`. Counts:
  `verified` = `RepairResult.verified` (not-stale verdicts); `auto_fixable` = AUTOFIX
  outcomes; `flagged` = FLAG outcomes; `skipped` = `sum(RepairResult.skipped.values())`.
- A backend-unavailable `RuntimeError` propagates (surfaced as a 502 at the API boundary,
  §4.3).

### 4.3 FastAPI app (`webapp/app.py`)
- JSON API only (it does **not** serve the frontend — the SPA is a separate Vercel deploy).
  `GET /healthz` → `{"status": "ok"}` (deploy health check). FastAPI's auto OpenAPI/Swagger
  docs at `/docs` come for free.
- **CORS:** `CORSMiddleware` with an allowlist of origins from a `CORS_ORIGINS` env var
  (the deployed Vercel URL + `http://localhost:5173` for Vite dev); no wildcard in the
  deployed config.
- `POST /api/analyze` — body `AnalyzeRequest`
  (`pr_url: str`, `backend: Literal["ollama","claude","fake"] = "ollama"`,
  `api_key: str | None`, `ollama_host: str | None`, `model: str | None`). Calls
  `service.analyze(...)`. Returns the `AnalyzeResult` JSON on success. Maps failures to clean
  HTTP errors: `ValueError` (bad URL / not found / too large) → **400** with the message;
  backend-unavailable `RuntimeError` → **502** with the actionable message; unexpected →
  **500** (generic message; details logged, never the credential). Enforces the request cap
  (§6).

### 4.4 Frontend (`frontend/` — React + TypeScript + Vite)
A Vite SPA in TypeScript, styled with **Tailwind CSS** + **shadcn/ui**, using **TanStack
Query** for the `POST /api/analyze` call (loading/error/success states handled by the query).
Structure: a small set of components — an `AnalyzeForm` (PR URL input; backend toggle
`ollama`/`claude`; a credential field whose label switches Ollama-host vs Anthropic-key; an
optional model field; **Analyze** button), a `ResultsPanel` (summary line
`N verified · M auto-fixable · K flagged · J skipped`), and a `SectionCard` (route badge, a
0–1 confidence bar, reason, wrong-claims list, collapsible unified-diff `<pre>`), plus an
error banner. A typed API client (`src/api.ts`) reads the backend base URL from
`import.meta.env.VITE_API_BASE` (defaults to `http://localhost:8000` in dev). TypeScript
interfaces mirror the API's `AnalyzeResult`/`SectionResult`. A **prefilled example PR URL**
enables a one-click try. The credential is sent only to the configured API and never
persisted.

### 4.5 Packaging & run modes
- **Backend** (`webapp/`): web deps (`fastapi`, `uvicorn[standard]`) in a **separate
  `requirements-web.txt`** so the core/Action install stays lean.
- **Frontend** (`frontend/`): a standard Vite React-TS project (`package.json`,
  `vite.config.ts`, `tailwind.config.js`, `tsconfig.json`).
- **Local dev:** `make api` → `uvicorn webapp.app:app --port 8000` (defaults backend
  `ollama`, host `http://localhost:11434`); `make web` → `npm --prefix frontend run dev`
  (Vite on `:5173`, `VITE_API_BASE=http://localhost:8000`). The author opens `localhost:5173`
  and analyzes a real PR on local Ollama at **$0**.
- **Public deploy:** the **frontend** deploys to **Vercel** (static build; `VITE_API_BASE`
  set to the backend URL). The **backend** deploys via `Dockerfile.web` (installs core + web
  deps, runs uvicorn, needs `git`) to a **free tier (Hugging Face Spaces — Docker; Render
  free the fallback)**, with `CORS_ORIGINS` set to the Vercel origin. No Ollama in the cloud,
  so the visitor uses **Claude + their own key**. README documents both modes and both
  deploys.

---

## 5. Data contracts (shared, fixed up front)

- `AnalyzeRequest` (Pydantic model in `webapp/app.py`): `pr_url: str`,
  `backend: str = "ollama"`, `api_key: str | None = None`, `ollama_host: str | None = None`,
  `model: str | None = None`.
- `SectionResult` / `AnalyzeResult` as in §4.2 (frozen dataclasses; serialized to JSON via
  `dataclasses.asdict`).
- The frontend mirrors these in `frontend/src/types.ts` as TypeScript interfaces
  (`AnalyzeRequest`, `SectionResult`, `AnalyzeResult`) — the single source of truth for the
  wire shape is this section; the Python dataclasses and the TS interfaces must match it.
- `Settings` is built in `analyze` from the request: `llm_backend=backend`,
  `ollama_host=ollama_host or default`, `claude_model=model or default` /
  `ollama_model=model or default`. The Anthropic key is plumbed to the environment the same
  way the Action does it (set `ANTHROPIC_API_KEY` from `api_key` for the duration of the
  request, in a `try/finally` that restores/clears it) so `make_client("claude")` → the
  lazily-constructed `anthropic.Anthropic()` picks it up.

---

## 6. Security & limits

- **CORS allowlist:** the API accepts cross-origin requests only from configured origins
  (`CORS_ORIGINS` — the Vercel URL + localhost dev), not `*`.
- **URL allowlist:** only `https://github.com/{owner}/{repo}/pull/{n}` with a `github.com`
  host; anything else → 400. No SSRF surface beyond the GitHub API + the clone.
- **Credentials:** per-request only; never logged, never written to disk; the 500 path logs
  no request body.
- **Resource caps:** shallow clone; reject a repo whose reported size exceeds a limit (from
  the GitHub API `size` field) → 400; an overall per-request timeout; the temp dir removed in
  a `finally`. A simple in-process concurrency/rate cap guards the public deploy.
- **`embeddings=False` by default:** no embedding-model download at runtime, faster; linking
  falls back to symbol-name matching (lower recall — documented). (A future toggle could
  enable embeddings.)
- Repo content is only **parsed** (tree-sitter), never executed.

---

## 7. Error handling

- Bad/unsupported URL, missing/private repo, oversized repo → **400** with a clear message.
- Backend unavailable (Ollama unreachable / missing-or-invalid Claude key) → the pipeline's
  `RuntimeError` propagates → **502** with the actionable message ("start Ollama…" / "check
  your Anthropic key").
- A single suspect's malformed LLM reply is skipped-and-counted inside `repair_pr` (existing
  behavior) and surfaces in `summary.skipped` — one bad section never fails the whole run.
- Unexpected errors → **500** generic; the temp dir is always cleaned up.

---

## 8. Testing ($0 / offline in CI)

- **Unit:** `parse_pr_url` (valid → tuple; rejects non-github, wrong path, http); the
  RepairResult→`AnalyzeResult` shaping over a synthetic `RepairResult`; `fetch_pr` with the
  GitHub API (`urllib`) and `git` monkeypatched (asserts it parses the API response and
  issues the right clone/fetch, no real network).
- **Integration (FastAPI `TestClient`, offline):** `POST /api/analyze` with `fetch_pr`
  monkeypatched to materialize a **fixture git repo** (reuse the evaluation materializer
  pattern: base commit + head commit changing a documented symbol) and `backend="fake"` (or a
  monkeypatched `make_client` returning a scripted `FakeLLMClient`) → asserts the JSON
  `summary` counts and a stale `SectionResult` with a proposed diff. Also asserts a bad URL →
  400 and a backend `RuntimeError` → 502. No network, no LLM, no key.
- **Frontend (Vitest + React Testing Library, offline):** the API client (`src/api.ts`)
  with `fetch` mocked → parses a fixture `AnalyzeResult`; `SectionCard` renders a route
  badge + diff from a fixture; `AnalyzeForm` toggles the credential label with the backend.
  Kept light. `npm run build` (type-check + bundle) must succeed.
- **Gated real end-to-end (manual):** a real public PR + local Ollama, skipped unless an
  env var is set — proves the live path; not run in CI.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Cloud backend can't reach a visitor's localhost Ollama | Two run modes: local+Ollama (author, $0) and deploy+Claude-BYO-key (public); documented. |
| Author has no paid budget to demo the public deploy | The **local** mode runs on free Ollama — the author visualizes the full product at $0; the public URL is the résumé artifact. |
| Cloning/indexing an arbitrary repo is heavy on a free tier | `embeddings=False`, shallow clone, repo-size cap, request timeout, temp-dir cleanup; public repos only. |
| Handling a visitor's Anthropic key | Per-request only, never stored/logged; set into the env in a `try/finally`; HTTPS at the deploy edge. |
| Untrusted repo content | Only parsed with tree-sitter, never executed; isolated temp dir. |
| Importing web modules pulls a heavy SDK | LLM SDK stays lazily imported (existing seam); web deps isolated in `requirements-web.txt`. |

---

## 10. Definition of Done

- Locally, `make api` + `make web` run the backend and the React SPA; pasting a real public
  PR URL with the Ollama backend shows staleness verdicts + proposed fix diffs, at **$0**,
  read-only.
- The frontend deploys to **Vercel** and the Dockerized backend to a **free tier**, wired via
  `VITE_API_BASE` + `CORS_ORIGINS`, and works with a visitor-supplied Anthropic key.
- `POST /api/analyze` returns the documented JSON; bad URLs → 400, backend-unavailable → 502;
  `/docs` serves the OpenAPI UI.
- Default `pytest` suite stays fully offline ($0) and green; `ruff check .` clean; importing
  the web modules needs no network/key. The frontend `npm run build` and its Vitest suite pass.
- README documents both local run and both deploys (Vercel + backend), with the public URL.
