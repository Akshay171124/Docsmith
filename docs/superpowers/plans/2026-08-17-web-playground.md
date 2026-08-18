# Web Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A $0, read-only web playground — paste a public GitHub PR URL, get Docsmith's staleness verdicts + proposed fix diffs — as a decoupled React+TS+Vite SPA talking to a Dockerized FastAPI API that wraps the existing pipeline.

**Architecture:** A FastAPI JSON API (`webapp/`) fetches a public PR into a temp dir, builds an index, runs `investigate_pr` + `repair_pr`, and shapes the result into JSON. A React + TypeScript + Vite SPA (`frontend/`) calls it over CORS and renders the results. The two deploy separately (backend Docker on a free tier, frontend on Vercel).

**Tech Stack:** Python 3.11+, FastAPI + Pydantic + uvicorn (backend); React 18 + TypeScript + Vite 5 + Tailwind v3 + shadcn/ui + TanStack Query (frontend); Node 22/npm 10; pytest + Vitest.

## Global Constraints

- **$0 / stateless:** no database, no persisted secrets. The LLM backend is bring-your-own via the existing `make_client` seam; the Anthropic key (when given) is used per-request only, set into `ANTHROPIC_API_KEY` in a `try/finally`, and **never logged or persisted**. Tests use the offline `fake` backend — no network, no key.
- **Read-only:** the playground never posts to GitHub. Public repos only.
- **URL allowlist:** only `https://github.com/{owner}/{repo}/pull/{n}` (host must be `github.com`); anything else → `ValueError` → HTTP 400.
- **Error mapping:** `ValueError` (bad URL / not found / too large) → **400**; backend-unavailable `RuntimeError` (Ollama down / bad Claude key) → **502**; unexpected → **500** (generic; details logged, never the credential).
- **`embeddings=False` by default** in the playground (no model download; symbol-match linking).
- **Two pipeline calls:** `analyze` runs both `investigate_pr` (for verdict `confidence`/`reason`/`wrong_claims`) and `repair_pr` (for `route`/`diff`), joined per `(symbol_id, section_id)` — the verdict fields are not on `RepairOutcome`.
- **Backend Python:** ruff line-length 100, select E/F/I/UP/B; docstrings Args/Returns/Raises; the default `pytest` suite stays fully offline and green; `ruff check .` clean; importing `webapp.*` needs no network/key (the LLM SDK stays lazily imported).
- **Frontend:** the `frontend/` Vitest suite and `npm run build` (type-check + bundle) must pass. Frontend tests run via `npm --prefix frontend test`, **not** the Python CI (`.github/workflows/ci.yml` runs ruff+pytest only — leave it as-is).
- TDD (failing test first); frequent commits; **no LLM/AI attribution** in any commit. Do NOT edit `docs/planning/roadmap.md` or `CHANGELOG.md` — living docs are controller-managed.

---

## File Structure

- `requirements-web.txt` (create) — backend web deps, separate from core.
- `webapp/__init__.py`, `webapp/prfetch.py`, `webapp/service.py`, `webapp/app.py` (create) — the API.
- `Dockerfile.web` (create), `Makefile` (modify — `api`/`web` targets).
- `frontend/` (create) — Vite React-TS app: `package.json`, `vite.config.ts`, `tsconfig*.json`, `tailwind.config.js`, `postcss.config.js`, `index.html`, `src/{main.tsx,App.tsx,index.css,types.ts,api.ts}`, `src/components/{AnalyzeForm,SectionCard,ResultsPanel}.tsx`, tests, `vercel.json`.
- `README.md` (modify) — playground run + deploy docs.
- Backend tests under `tests/` (`tests/unit/test_prfetch.py`, `tests/integration/test_webapp_service.py`, `tests/integration/test_webapp_app.py`). Frontend tests colocated under `frontend/src/`.

---

## Task 0: Backend scaffolding (web deps + package)

**Files:**
- Create: `requirements-web.txt`, `webapp/__init__.py`
- Test: `tests/unit/test_webapp_scaffold.py`

**Interfaces — Produces:** an importable `webapp` package; `fastapi`/`uvicorn`/`httpx` installed.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_webapp_scaffold.py`:

```python
def test_webapp_package_and_fastapi_importable():
    import fastapi  # from requirements-web.txt
    import webapp  # the new package

    assert fastapi.FastAPI is not None
    assert webapp.__doc__  # package has a module docstring
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_webapp_scaffold.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'webapp'` (or `fastapi` not installed).

- [ ] **Step 3: Create the deps file + install**

Create `requirements-web.txt`:

```
# Docsmith web playground API — kept separate from requirements.txt so the core
# library / GitHub Action install stays lean.
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27          # used by fastapi.testclient.TestClient
```

Install: `pip install -r requirements-web.txt`

- [ ] **Step 4: Create the package**

Create `webapp/__init__.py`:

```python
"""Docsmith web playground: a FastAPI JSON API wrapping the analysis pipeline."""
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_webapp_scaffold.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements-web.txt webapp/__init__.py tests/unit/test_webapp_scaffold.py
git commit -m "chore: scaffold web playground backend package and deps"
```

---

## Task 1: PR URL parsing

**Files:**
- Create: `webapp/prfetch.py`
- Test: `tests/unit/test_prfetch.py`

**Interfaces — Produces:** `parse_pr_url(url: str) -> tuple[str, str, int]` — `(owner, repo, number)`; raises `ValueError` for anything that is not a public `github.com` PR URL.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_prfetch.py`:

```python
import pytest

from webapp.prfetch import parse_pr_url


def test_parses_valid_pr_url():
    assert parse_pr_url("https://github.com/octo/repo/pull/42") == ("octo", "repo", 42)


def test_parses_with_trailing_slash():
    assert parse_pr_url("https://github.com/octo/repo/pull/42/") == ("octo", "repo", 42)


@pytest.mark.parametrize("bad", [
    "http://github.com/octo/repo/pull/42",       # not https
    "https://gitlab.com/octo/repo/pull/42",      # not github
    "https://github.com/octo/repo/issues/42",    # not a PR
    "https://github.com/octo/repo/pull/abc",     # non-numeric
    "https://github.com/octo/repo",              # no PR
    "not a url",
])
def test_rejects_bad_urls(bad):
    with pytest.raises(ValueError):
        parse_pr_url(bad)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_prfetch.py -v`
Expected: FAIL — `webapp.prfetch` does not exist.

- [ ] **Step 3: Implement**

Create `webapp/prfetch.py`:

```python
"""Fetch a public GitHub pull request into a scratch git repo for analysis."""

from __future__ import annotations

import re

_PR_URL_RE = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)/?$")


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse a public GitHub PR URL into ``(owner, repo, number)``.

    Args:
        url: A ``https://github.com/{owner}/{repo}/pull/{n}`` URL.

    Returns:
        The ``(owner, repo, number)`` triple.

    Raises:
        ValueError: If ``url`` is not a public GitHub pull-request URL.
    """
    match = _PR_URL_RE.match(url.strip())
    if match is None:
        raise ValueError(f"not a public GitHub pull-request URL: {url!r}")
    owner, repo, number = match.group(1), match.group(2), int(match.group(3))
    return owner, repo, number
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_prfetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webapp/prfetch.py tests/unit/test_prfetch.py
git commit -m "feat: parse public GitHub PR URLs"
```

---

## Task 2: PR fetch (GitHub API + git clone)

**Files:**
- Modify: `webapp/prfetch.py`
- Test: `tests/unit/test_prfetch.py`

**Interfaces:**
- Consumes: `parse_pr_url`.
- Produces: `fetch_pr(pr_url: str, workdir: str, *, token: str | None = None) -> tuple[str, str, str]` — returns `(repo_path, base_sha, head_sha)` with both commits present in the clone (the PR head is fetched via the `pull/{n}/head` ref). Also the module constant `MAX_REPO_KB: int`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_prfetch.py`:

```python
import json
from unittest.mock import MagicMock

import webapp.prfetch as prfetch


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


_PR_JSON = {
    "number": 7,
    "base": {"sha": "basesha", "repo": {"clone_url": "https://github.com/octo/repo.git", "size": 1000}},
    "head": {"sha": "headsha", "repo": {"clone_url": "https://github.com/octo/repo.git"}},
}


def test_fetch_pr_clones_and_returns_shas(tmp_path, monkeypatch):
    monkeypatch.setattr(prfetch.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(_PR_JSON))
    calls = []
    monkeypatch.setattr(prfetch.subprocess, "run", lambda cmd, **k: calls.append(cmd) or MagicMock())

    repo, base, head = prfetch.fetch_pr("https://github.com/octo/repo/pull/7", str(tmp_path))

    assert base == "basesha" and head == "headsha"
    assert repo.endswith("repo")
    assert any(c[:2] == ["git", "clone"] for c in calls)               # cloned the base repo
    assert any("pull/7/head" in " ".join(c) for c in calls)            # fetched the PR head ref


def test_fetch_pr_rejects_oversized_repo(tmp_path, monkeypatch):
    big = json.loads(json.dumps(_PR_JSON))
    big["base"]["repo"]["size"] = prfetch.MAX_REPO_KB + 1
    monkeypatch.setattr(prfetch.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(big))
    with pytest.raises(ValueError, match="too large"):
        prfetch.fetch_pr("https://github.com/octo/repo/pull/7", str(tmp_path))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_prfetch.py -k fetch_pr -v`
Expected: FAIL — `fetch_pr` / `MAX_REPO_KB` not defined.

- [ ] **Step 3: Implement**

Add to the top of `webapp/prfetch.py` (imports) and append the function:

```python
import json
import os
import subprocess
import urllib.error
import urllib.request

MAX_REPO_KB = 200_000  # ~200 MB reported repo size cap for the playground


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def fetch_pr(pr_url: str, workdir: str, *, token: str | None = None) -> tuple[str, str, str]:
    """Clone a public PR's base repo into ``workdir`` and fetch its head commit.

    Args:
        pr_url: A public GitHub pull-request URL.
        workdir: A directory to create the clone under.
        token: Optional GitHub token — only raises the API rate limit.

    Returns:
        ``(repo_path, base_sha, head_sha)``; both commits are present in the clone.

    Raises:
        ValueError: If the URL is invalid, the PR/repo is missing (404), or the repo
            exceeds the size cap.
    """
    owner, repo, number = parse_pr_url(pr_url)
    api = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    request = urllib.request.Request(
        api, headers={"Accept": "application/vnd.github+json", "User-Agent": "docsmith-playground"}
    )
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError("PR or repository not found (must be a public GitHub PR)") from exc
        raise

    size_kb = data["base"]["repo"].get("size", 0)
    if size_kb > MAX_REPO_KB:
        raise ValueError(f"repository too large for the playground ({size_kb} KB)")

    base_sha = data["base"]["sha"]
    head_sha = data["head"]["sha"]
    clone_url = data["base"]["repo"]["clone_url"]

    repo_path = os.path.join(workdir, "repo")
    _git("clone", clone_url, repo_path)
    # The PR head is reachable via GitHub's pull/<n>/head ref on the base repo (fork-safe).
    _git("-C", repo_path, "fetch", "origin", f"pull/{number}/head")
    return repo_path, base_sha, head_sha
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_prfetch.py -v`
Expected: PASS.

- [ ] **Step 5: Ruff + commit**

Run: `python3 -m ruff check webapp/prfetch.py tests/unit/test_prfetch.py`
Then:

```bash
git add webapp/prfetch.py tests/unit/test_prfetch.py
git commit -m "feat: fetch a public PR into a scratch git repo"
```

---

## Task 3: Analyze service

**Files:**
- Create: `webapp/service.py`
- Test: `tests/integration/test_webapp_service.py`

**Interfaces:**
- Consumes: `fetch_pr`; `build_index` (`src/index/builder.py`); `investigate_pr`, `make_client` (`src/detection/investigator.py`); `repair_pr` (`src/repair/engine.py`); `Settings` (`src/utils/config.py`); the eval `materialize_case` + `Case`/`Gold` for the test fixture.
- Produces: `SectionResult` (frozen: `file`, `section_id`, `route`, `confidence`, `reason`, `wrong_claims: list[str]`, `diff`), `AnalyzeResult` (frozen: `summary: dict[str,int]`, `results: list[SectionResult]`), and `analyze(pr_url, backend, *, api_key=None, ollama_host=None, model=None, embeddings=False) -> AnalyzeResult`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_webapp_service.py`:

```python
import webapp.service as service
from evaluation.materialize import materialize_case
from evaluation.models import Case, Gold
from src.llm.client import FakeLLMClient

CASE = Case(
    case_id="pr",
    base_files={
        "app.py": "def create_user(name):\n    return {\"name\": name}\n",
        "README.md": "# App\n\n## Users\n\nCall `create_user` with a name.\n",
    },
    head_files={
        "app.py": "def create_user(name, email):\n    return {\"name\": name, \"email\": email}\n",
        "README.md": "# App\n\n## Users\n\nCall `create_user` with a name.\n",
    },
    gold=Gold(stale_section_ids=frozenset({"README.md#users"})),
)


def _pipeline_client() -> FakeLLMClient:
    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": "Call `create_user` with a name and email."}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        return {"stale": True, "confidence": 0.9, "reason": "signature changed",
                "wrong_claims": ["create_user"]}
    return FakeLLMClient(respond)


def test_analyze_shapes_stale_section(tmp_path, monkeypatch):
    def fake_fetch(pr_url, workdir, *, token=None):
        return materialize_case(CASE, workdir)  # (repo, base, head)

    monkeypatch.setattr(service, "fetch_pr", fake_fetch)
    monkeypatch.setattr(service, "make_client", lambda settings, backend_override=None: _pipeline_client())

    result = service.analyze("https://github.com/o/r/pull/1", "fake", embeddings=False)

    assert result.summary["auto_fixable"] == 1
    assert len(result.results) == 1
    section = result.results[0]
    assert section.section_id == "README.md#users"
    assert section.file == "README.md"
    assert section.route == "autofix"
    assert section.confidence == 0.9
    assert "create_user" in section.reason or section.wrong_claims == ["create_user"]
    assert "create_user(name, email)" in section.diff
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_webapp_service.py -v`
Expected: FAIL — `webapp.service` does not exist.

- [ ] **Step 3: Implement**

Create `webapp/service.py`:

```python
"""Analyze a public PR through the Docsmith pipeline and shape the output as JSON."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from src.detection.investigator import investigate_pr, make_client
from src.index.builder import build_index
from src.repair.engine import repair_pr
from src.utils.config import Settings
from webapp.prfetch import fetch_pr


@dataclass(frozen=True)
class SectionResult:
    """One stale documentation section and its proposed fix.

    Attributes:
        file: Doc file path. section_id: ``file#slug`` identifier.
        route: ``autofix`` / ``flag`` / ``skipped``. confidence: staleness confidence (0-1).
        reason: the investigator's explanation. wrong_claims: now-inaccurate statements.
        diff: unified diff of the proposed correction (empty when none).
    """

    file: str
    section_id: str
    route: str
    confidence: float
    reason: str
    wrong_claims: list[str]
    diff: str


@dataclass(frozen=True)
class AnalyzeResult:
    """The playground's analysis of a PR.

    Attributes:
        summary: counts (``verified``/``auto_fixable``/``flagged``/``skipped``).
        results: one entry per stale section.
    """

    summary: dict[str, int]
    results: list[SectionResult]


def _shape(inv_result, repair_result) -> AnalyzeResult:
    outcome_by_key = {
        (o.proposal.symbol_id, o.proposal.section_id): o for o in repair_result.outcomes
    }
    results: list[SectionResult] = []
    for verdict in inv_result.verdicts:
        if not verdict.stale:
            continue
        outcome = outcome_by_key.get((verdict.symbol_id, verdict.section_id))
        results.append(
            SectionResult(
                file=verdict.section_id.rsplit("#", 1)[0],
                section_id=verdict.section_id,
                route=outcome.route.value if outcome else "skipped",
                confidence=verdict.confidence,
                reason=verdict.reason,
                wrong_claims=list(verdict.wrong_claims),
                diff=outcome.proposal.diff if outcome else "",
            )
        )
    summary = {
        "verified": repair_result.verified,
        "auto_fixable": sum(1 for o in repair_result.outcomes if o.route.value == "autofix"),
        "flagged": sum(1 for o in repair_result.outcomes if o.route.value == "flag"),
        "skipped": sum(repair_result.skipped.values()),
    }
    return AnalyzeResult(summary=summary, results=results)


def analyze(
    pr_url: str,
    backend: str,
    *,
    api_key: str | None = None,
    ollama_host: str | None = None,
    model: str | None = None,
    embeddings: bool = False,
) -> AnalyzeResult:
    """Fetch a public PR, run detection→investigation→repair, and shape the result.

    Args:
        pr_url: A public GitHub PR URL.
        backend: LLM backend (``ollama``/``claude``/``fake``).
        api_key: Anthropic key (Claude only); used per-request, never stored.
        ollama_host: Ollama base URL override.
        model: Model name override for the chosen backend.
        embeddings: Whether to build the index with embeddings (default False for speed).

    Returns:
        An AnalyzeResult.

    Raises:
        ValueError: Bad URL / missing / oversized repo.
        RuntimeError: Backend unavailable (propagated from the LLM client).
    """
    settings = Settings()
    settings.llm_backend = backend
    if ollama_host:
        settings.ollama_host = ollama_host
    if model:
        if backend == "claude":
            settings.claude_model = model
        else:
            settings.ollama_model = model

    previous_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    workdir = tempfile.TemporaryDirectory()
    try:
        repo, base, head = fetch_pr(pr_url, workdir.name)
        index_path = os.path.join(workdir.name, "index.json")
        build_index(repo, output_path=index_path, embeddings=embeddings, full=True)
        client = make_client(settings, backend_override=backend)
        inv_result = investigate_pr(repo, base, head, index_path, settings, client)
        repair_result = repair_pr(repo, base, head, index_path, settings, client)
        return _shape(inv_result, repair_result)
    finally:
        workdir.cleanup()
        if api_key:
            if previous_key is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = previous_key
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_webapp_service.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + ruff + commit**

Run: `python3 -m pytest -q && python3 -m ruff check webapp`
Then:

```bash
git add webapp/service.py tests/integration/test_webapp_service.py
git commit -m "feat: analyze service shapes pipeline output for the web API"
```

---

## Task 4: FastAPI app + Dockerfile + Makefile target

**Files:**
- Create: `webapp/app.py`, `Dockerfile.web`
- Modify: `Makefile`
- Test: `tests/integration/test_webapp_app.py`

**Interfaces:**
- Consumes: `webapp.service` (`analyze`, `AnalyzeResult`).
- Produces: a FastAPI `app` with `GET /healthz`, `POST /api/analyze` (body `AnalyzeRequest`), CORS from `CORS_ORIGINS`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_webapp_app.py`:

```python
import pytest
from fastapi.testclient import TestClient

import webapp.app as appmod
from webapp.app import app
from webapp.service import AnalyzeResult

client = TestClient(app)


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_analyze_ok(monkeypatch):
    monkeypatch.setattr(
        appmod.service, "analyze",
        lambda *a, **k: AnalyzeResult(summary={"verified": 1, "auto_fixable": 1, "flagged": 0, "skipped": 0}, results=[]),
    )
    resp = client.post("/api/analyze", json={"pr_url": "https://github.com/o/r/pull/1", "backend": "fake"})
    assert resp.status_code == 200
    assert resp.json()["summary"]["auto_fixable"] == 1


def test_bad_url_returns_400():
    # real path — parse_pr_url inside analyze raises ValueError before any network
    resp = client.post("/api/analyze", json={"pr_url": "not-a-url", "backend": "fake"})
    assert resp.status_code == 400


def test_backend_unavailable_returns_502(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Could not reach Ollama")
    monkeypatch.setattr(appmod.service, "analyze", boom)
    resp = client.post("/api/analyze", json={"pr_url": "https://github.com/o/r/pull/1", "backend": "ollama"})
    assert resp.status_code == 502
    assert "Ollama" in resp.json()["detail"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_webapp_app.py -v`
Expected: FAIL — `webapp.app` does not exist.

- [ ] **Step 3: Implement the app**

Create `webapp/app.py`:

```python
"""FastAPI JSON API for the Docsmith web playground."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from webapp import service

logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    """Request body for ``POST /api/analyze``."""

    pr_url: str
    backend: str = "ollama"
    api_key: str | None = None
    ollama_host: str | None = None
    model: str | None = None


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Docsmith Playground API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe for the deploy platform."""
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    """Analyze a public PR and return staleness verdicts + proposed fixes.

    Raises:
        HTTPException: 400 (bad URL / missing / oversized), 502 (backend unavailable),
            500 (unexpected).
    """
    try:
        result = service.analyze(
            request.pr_url,
            request.backend,
            api_key=request.api_key,
            ollama_host=request.ollama_host,
            model=request.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface a generic 500, never the credential
        logger.exception("analyze failed")
        raise HTTPException(status_code=500, detail="internal error") from exc
    return asdict(result)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_webapp_app.py -v`
Expected: PASS.

- [ ] **Step 5: Add the Dockerfile + Makefile target**

Create `Dockerfile.web`:

```dockerfile
# Docsmith web playground API.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-web.txt ./
RUN pip install -r requirements.txt -r requirements-web.txt

COPY . .

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn webapp.app:app --host 0.0.0.0 --port ${PORT}"]
```

In `Makefile`, add `api` to `.PHONY` and the target (leave existing targets untouched):

```makefile
.PHONY: api
api:
	uvicorn webapp.app:app --reload --port 8000
```

- [ ] **Step 6: Full suite + ruff + commit**

Run: `python3 -m pytest -q && python3 -m ruff check webapp docsmith.py`
Then:

```bash
git add webapp/app.py Dockerfile.web Makefile tests/integration/test_webapp_app.py
git commit -m "feat: FastAPI playground API with CORS and error mapping"
```

---

## Task 5: Frontend scaffold (Vite + React + TS + Tailwind + Vitest)

**Files:**
- Create: `frontend/` (Vite React-TS project + Tailwind + Vitest + TanStack Query provider)
- Modify: `Makefile` (`web` target)
- Test: `frontend/src/App.test.tsx`

**Interfaces — Produces:** a buildable Vite app rendering `<App/>` inside a `QueryClientProvider`; `npm --prefix frontend run build` and `npm --prefix frontend test` both succeed.

- [ ] **Step 1: Scaffold the Vite React-TS project**

Run (non-interactive):

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install @tanstack/react-query
npm install -D tailwindcss@3 postcss autoprefixer vitest @testing-library/react @testing-library/jest-dom jsdom
npx tailwindcss init -p
cd ..
```

- [ ] **Step 2: Configure Tailwind + Vitest + a test setup**

Overwrite `frontend/tailwind.config.js`:

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

Overwrite `frontend/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Overwrite `frontend/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.ts",
  },
});
```

Create `frontend/src/setupTests.ts`:

```ts
import "@testing-library/jest-dom";
```

Add a `test` script to `frontend/package.json`'s `"scripts"`: `"test": "vitest run"`.

- [ ] **Step 3: Write the failing test**

Overwrite `frontend/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the playground heading", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /docsmith/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run to verify it fails**

Run: `npm --prefix frontend test`
Expected: FAIL — `App` doesn't render the heading yet (or App still the Vite template).

- [ ] **Step 5: Implement App shell + main entry**

Overwrite `frontend/src/main.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
```

Overwrite `frontend/src/App.tsx`:

```tsx
export default function App() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-bold">Docsmith Playground</h1>
      <p className="mt-2 text-gray-600">
        Paste a public GitHub PR URL to see which docs it made stale.
      </p>
    </main>
  );
}
```

- [ ] **Step 6: Run test + build**

Run: `npm --prefix frontend test && npm --prefix frontend run build`
Expected: test PASS; build succeeds (type-check + bundle).

- [ ] **Step 7: Add the Makefile web target + commit**

In `Makefile`, add `web` to `.PHONY` and:

```makefile
.PHONY: web
web:
	npm --prefix frontend run dev
```

Ensure `frontend/node_modules` and `frontend/dist` are git-ignored (add to `.gitignore` if not covered).

```bash
git add frontend Makefile .gitignore
git commit -m "chore: scaffold React+TS+Vite frontend with Tailwind and Vitest"
```

---

## Task 6: Types + typed API client

**Files:**
- Create: `frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/api.test.ts`

**Interfaces — Produces:** TS interfaces `AnalyzeRequest`, `SectionResult`, `AnalyzeResult` (mirroring the backend); `analyzePr(req: AnalyzeRequest): Promise<AnalyzeResult>` posting to `${VITE_API_BASE}/api/analyze`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzePr } from "./api";
import type { AnalyzeResult } from "./types";

const RESULT: AnalyzeResult = {
  summary: { verified: 1, auto_fixable: 1, flagged: 0, skipped: 0 },
  results: [
    {
      file: "README.md", section_id: "README.md#users", route: "autofix",
      confidence: 0.9, reason: "signature changed", wrong_claims: ["create_user"],
      diff: "-old\n+new",
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe("analyzePr", () => {
  it("posts and parses the result", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(RESULT), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const out = await analyzePr({ pr_url: "https://github.com/o/r/pull/1", backend: "fake" });
    expect(out.summary.auto_fixable).toBe(1);
    expect(out.results[0].section_id).toBe("README.md#users");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("throws with the API detail on error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "bad url" }), { status: 400 }),
    ));
    await expect(analyzePr({ pr_url: "x", backend: "fake" })).rejects.toThrow("bad url");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix frontend test -- api`
Expected: FAIL — `./api` / `./types` do not exist.

- [ ] **Step 3: Implement types + client**

Create `frontend/src/types.ts`:

```ts
export interface AnalyzeRequest {
  pr_url: string;
  backend: "ollama" | "claude" | "fake";
  api_key?: string | null;
  ollama_host?: string | null;
  model?: string | null;
}

export interface SectionResult {
  file: string;
  section_id: string;
  route: string;
  confidence: number;
  reason: string;
  wrong_claims: string[];
  diff: string;
}

export interface AnalyzeResult {
  summary: { verified: number; auto_fixable: number; flagged: number; skipped: number };
  results: SectionResult[];
}
```

Create `frontend/src/api.ts`:

```ts
import type { AnalyzeRequest, AnalyzeResult } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function analyzePr(request: AnalyzeRequest): Promise<AnalyzeResult> {
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `request failed (${response.status})`);
  }
  return (await response.json()) as AnalyzeResult;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm --prefix frontend test -- api`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat: typed API client for the playground"
```

---

## Task 7: UI components + App wiring

**Files:**
- Create: `frontend/src/components/{AnalyzeForm,SectionCard,ResultsPanel}.tsx`, `frontend/src/components/AnalyzeForm.test.tsx`, `frontend/src/components/SectionCard.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `analyzePr`, the TS types, `useMutation` from `@tanstack/react-query`.
- Produces: the three components + an `App` that runs the analysis via a mutation and renders results/errors.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/SectionCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SectionCard from "./SectionCard";
import type { SectionResult } from "../types";

const SECTION: SectionResult = {
  file: "README.md", section_id: "README.md#users", route: "autofix",
  confidence: 0.9, reason: "signature changed", wrong_claims: ["create_user"],
  diff: "-Use `create_user(name)`\n+Use `create_user(name, email)`",
};

describe("SectionCard", () => {
  it("shows the section id, route badge, and diff", () => {
    render(<SectionCard section={SECTION} />);
    expect(screen.getByText("README.md#users")).toBeInTheDocument();
    expect(screen.getByText(/autofix/i)).toBeInTheDocument();
    expect(screen.getByText(/create_user\(name, email\)/)).toBeInTheDocument();
  });
});
```

Create `frontend/src/components/AnalyzeForm.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AnalyzeForm from "./AnalyzeForm";

describe("AnalyzeForm", () => {
  it("switches the credential label with the backend", async () => {
    render(<AnalyzeForm onSubmit={vi.fn()} pending={false} />);
    expect(screen.getByLabelText(/ollama host/i)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/claude/i));
    expect(screen.getByLabelText(/anthropic api key/i)).toBeInTheDocument();
  });
});
```

(Install the interaction lib: `npm --prefix frontend install -D @testing-library/user-event`.)

- [ ] **Step 2: Run to verify they fail**

Run: `npm --prefix frontend test -- components`
Expected: FAIL — the components don't exist.

- [ ] **Step 3: Implement the components**

Create `frontend/src/components/SectionCard.tsx`:

```tsx
import type { SectionResult } from "../types";

const ROUTE_STYLE: Record<string, string> = {
  autofix: "bg-green-100 text-green-800",
  flag: "bg-yellow-100 text-yellow-800",
  skipped: "bg-gray-100 text-gray-600",
};

export default function SectionCard({ section }: { section: SectionResult }) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <code className="font-mono text-sm">{section.section_id}</code>
        <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${ROUTE_STYLE[section.route] ?? ""}`}>
          {section.route}
        </span>
      </div>
      <p className="mt-2 text-sm text-gray-700">{section.reason}</p>
      <div className="mt-2 h-1.5 w-full rounded bg-gray-200">
        <div className="h-1.5 rounded bg-blue-500" style={{ width: `${Math.round(section.confidence * 100)}%` }} />
      </div>
      {section.wrong_claims.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-sm text-gray-600">
          {section.wrong_claims.map((claim) => <li key={claim}>{claim}</li>)}
        </ul>
      )}
      {section.diff && (
        <pre className="mt-3 overflow-x-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{section.diff}</pre>
      )}
    </div>
  );
}
```

Create `frontend/src/components/ResultsPanel.tsx`:

```tsx
import type { AnalyzeResult } from "../types";
import SectionCard from "./SectionCard";

export default function ResultsPanel({ result }: { result: AnalyzeResult }) {
  const s = result.summary;
  return (
    <section className="mt-6">
      <p className="text-sm font-medium">
        {s.verified} verified · {s.auto_fixable} auto-fixable · {s.flagged} flagged · {s.skipped} skipped
      </p>
      <div className="mt-4 space-y-3">
        {result.results.map((section) => <SectionCard key={section.section_id} section={section} />)}
        {result.results.length === 0 && (
          <p className="text-sm text-gray-500">No stale documentation found for this PR. 🎉</p>
        )}
      </div>
    </section>
  );
}
```

Create `frontend/src/components/AnalyzeForm.tsx`:

```tsx
import { useState } from "react";
import type { AnalyzeRequest } from "../types";

const EXAMPLE = "https://github.com/octocat/Hello-World/pull/1";

export default function AnalyzeForm({
  onSubmit,
  pending,
}: {
  onSubmit: (req: AnalyzeRequest) => void;
  pending: boolean;
}) {
  const [prUrl, setPrUrl] = useState(EXAMPLE);
  const [backend, setBackend] = useState<"ollama" | "claude">("ollama");
  const [credential, setCredential] = useState("");
  const [model, setModel] = useState("");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    onSubmit({
      pr_url: prUrl,
      backend,
      api_key: backend === "claude" ? credential || null : null,
      ollama_host: backend === "ollama" ? credential || null : null,
      model: model || null,
    });
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="pr" className="block text-sm font-medium">Public GitHub PR URL</label>
        <input id="pr" value={prUrl} onChange={(e) => setPrUrl(e.target.value)}
          className="mt-1 w-full rounded border p-2 font-mono text-sm" />
      </div>
      <fieldset className="flex gap-4">
        <label className="flex items-center gap-1 text-sm">
          <input type="radio" name="backend" checked={backend === "ollama"}
            onChange={() => setBackend("ollama")} /> Ollama (local)
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="radio" name="backend" checked={backend === "claude"}
            onChange={() => setBackend("claude")} /> Claude
        </label>
      </fieldset>
      <div>
        <label htmlFor="cred" className="block text-sm font-medium">
          {backend === "claude" ? "Anthropic API key" : "Ollama host"}
        </label>
        <input id="cred" value={credential} onChange={(e) => setCredential(e.target.value)}
          type={backend === "claude" ? "password" : "text"}
          placeholder={backend === "claude" ? "sk-ant-…" : "http://localhost:11434"}
          className="mt-1 w-full rounded border p-2 text-sm" />
      </div>
      <div>
        <label htmlFor="model" className="block text-sm font-medium">Model (optional)</label>
        <input id="model" value={model} onChange={(e) => setModel(e.target.value)}
          className="mt-1 w-full rounded border p-2 text-sm" />
      </div>
      <button type="submit" disabled={pending}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">
        {pending ? "Analyzing…" : "Analyze"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Wire up App**

Overwrite `frontend/src/App.tsx`:

```tsx
import { useMutation } from "@tanstack/react-query";
import { analyzePr } from "./api";
import AnalyzeForm from "./components/AnalyzeForm";
import ResultsPanel from "./components/ResultsPanel";

export default function App() {
  const mutation = useMutation({ mutationFn: analyzePr });

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-bold">Docsmith Playground</h1>
      <p className="mt-2 text-gray-600">
        Paste a public GitHub PR URL to see which docs it made stale — read-only, never posts.
      </p>
      <div className="mt-6">
        <AnalyzeForm onSubmit={(req) => mutation.mutate(req)} pending={mutation.isPending} />
      </div>
      {mutation.isError && (
        <p className="mt-4 rounded bg-red-100 p-3 text-sm text-red-800">
          {(mutation.error as Error).message}
        </p>
      )}
      {mutation.isSuccess && <ResultsPanel result={mutation.data} />}
    </main>
  );
}
```

- [ ] **Step 5: Run tests + build**

Run: `npm --prefix frontend test && npm --prefix frontend run build`
Expected: all Vitest tests PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src frontend/package.json frontend/package-lock.json
git commit -m "feat: playground UI (form, results, section cards) wired via react-query"
```

---

## Task 8: Deploy config + README + gated end-to-end note

**Files:**
- Create: `frontend/vercel.json`, `frontend/.env.example`, `tests/integration/test_webapp_live.py`
- Modify: `README.md`

**Interfaces:** Consumes the built app + the API.

- [ ] **Step 1: Write the gated live test (skips cleanly)**

Create `tests/integration/test_webapp_live.py`:

```python
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_WEB_LIVE") != "1",
    reason="set DOCSMITH_RUN_WEB_LIVE=1 (+ Ollama running) to run the live web-analyze test",
)


def test_analyze_real_pr_on_ollama():
    from webapp.service import analyze

    pr_url = os.environ["DOCSMITH_WEB_TEST_PR"]  # a small public PR that touches code+docs
    result = analyze(pr_url, "ollama", embeddings=False)
    assert "verified" in result.summary
    assert isinstance(result.results, list)
```

- [ ] **Step 2: Verify it SKIPS cleanly**

Run: `python3 -m pytest tests/integration/test_webapp_live.py -rs -v`
Expected: `1 skipped` (reason shown), no collection error.

- [ ] **Step 3: Frontend deploy config**

Create `frontend/vercel.json`:

```json
{ "buildCommand": "npm run build", "outputDirectory": "dist", "framework": "vite" }
```

Create `frontend/.env.example`:

```
# Backend API base URL (set in Vercel project settings for the deployed frontend).
VITE_API_BASE=http://localhost:8000
```

- [ ] **Step 4: README section**

In `README.md`, add a **## Try it (web playground)** section documenting:
- Local dev: `make api` (FastAPI on :8000, defaults to local Ollama) + `make web` (Vite on :5173); open `http://localhost:5173`, paste a public PR URL → verdicts + proposed diffs at $0.
- Public deploy: frontend on **Vercel** (`frontend/`, set `VITE_API_BASE` to the backend URL); backend via `Dockerfile.web` on a **free tier** (Hugging Face Spaces / Render), set `CORS_ORIGINS` to the Vercel origin. In the cloud the visitor selects **Claude + their own key** (no code change).
- A one-line note that it's **read-only** (never posts to GitHub) and **public repos only**.

- [ ] **Step 5: Verify + commit**

Run: `python3 -m pytest -q -rs && python3 -m ruff check . && npm --prefix frontend run build`
Expected: Python suite green (web-live test skipped), ruff clean, frontend build succeeds.

```bash
git add frontend/vercel.json frontend/.env.example tests/integration/test_webapp_live.py README.md
git commit -m "feat: playground deploy config, docs, and gated live test"
```

---

## Definition of Done (from the spec)

- Locally, `make api` + `make web` run the backend and the React SPA; a real public PR URL with the Ollama backend shows staleness verdicts + proposed fix diffs, at **$0**, read-only.
- The frontend deploys to Vercel and the Dockerized backend to a free tier, wired via `VITE_API_BASE` + `CORS_ORIGINS`, working with a visitor-supplied Anthropic key.
- `POST /api/analyze` returns the documented JSON; bad URLs → 400, backend-unavailable → 502; `/docs` serves OpenAPI.
- Default `pytest` suite stays fully offline ($0) and green; `ruff check .` clean; `webapp.*` imports need no network/key. Frontend `npm run build` + Vitest pass.
- README documents both run modes and both deploys.
- No LLM/AI attribution in any commit; living docs updated by the controller.
