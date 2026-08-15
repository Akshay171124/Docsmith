# GitHub Action (Week 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the repair engine's `RepairResult` into real GitHub output on a pull request — an always-posted summary comment, one companion fix-PR for AUTOFIX corrections, and FLAG items rendered with proposed diffs — never auto-merging, and running at $0 on Ollama + `github.token`.

**Architecture:** A write-side `GitHubClient` seam (real `PyGithubClient` + `FakeGitHubClient`) behind which a Reporter posts a summary comment and opens/updates a companion fix-PR; a PR-context loader reads the Actions event; pure helpers build the summary markdown and apply AUTOFIX corrections to files; a `github-action` entrypoint wires inputs → settings → index → `repair_pr` → Reporter → outputs. The default test suite stays $0/offline behind the two fakes.

**Tech Stack:** Python 3.11+, PyGithub (lazy-imported), the existing `LLMClient`/index/repair stack, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-15-github-action-design.md`.

## Global Constraints

- **$0 cost posture (hard):** tests use `FakeGitHubClient` + `FakeLLMClient` — no network/token/key, in CI. The live Action runs on `OllamaClient` (default) + the free `github.token`. `ClaudeClient` is opt-in (`llm-backend: claude` + `anthropic-api-key`), never the default, never in the default suite.
- **Lazy SDK imports:** importing any module must never import `github` (PyGithub) or `anthropic`, open a socket, or need a token/key. The real clients import their SDK *inside* methods. A unit test asserts `github` is not imported at module load.
- **Never auto-merges.** The Action opens/updates PRs and comments; a human always merges. No summary/PR copy may imply auto-merge.
- **Idempotency:** re-runs UPDATE the same summary comment (found by the hidden marker `<!-- docsmith:summary -->`) and REUSE the deterministic fix branch `docsmith/fix-pr-{pr_number}` — never duplicating.
- **FLAG items render in the summary comment** (collapsible proposed diffs), NOT as inline review comments.
- **AUTOFIX file application is deterministic:** span-replace `DocSection.start_line..end_line` with `proposal.revised_text`; multiple edits to one file applied bottom-up (descending `start_line`) to avoid line drift; preserve the file's trailing newline.
- **Entrypoint is a `github-action` subcommand** (argparse subparsers are `required=True` in this repo). The `Dockerfile` ENTRYPOINT uses `github-action` (not `--github-action`).
- ruff line-length 100; docstrings with Args/Returns/Raises; TDD (failing test first); frequent commits; **no LLM/AI attribution** in any commit. Do NOT edit `docs/planning/roadmap.md` or `CHANGELOG.md` — living docs are controller-managed.

---

## File Structure

- `src/utils/config.py` (modify) — add `auto_fix: bool` to `Settings`; read top-level `auto_fix` in `load_settings`.
- `src/detection/models.py` (modify) — add `RepairResult.verified: int`.
- `src/repair/engine.py` (modify) — populate `verified` in `repair_pr`.
- `src/github/context.py` (create) — `PRContext`, `load_pr_context`.
- `src/github/apply.py` (create) — `apply_corrections`.
- `src/github/summary.py` (create) — `MARKER`, `build_summary`.
- `src/github/client.py` (replace stub) — `GitHubClient` protocol, `FakeGitHubClient`, `PyGithubClient`.
- `src/github/reporter.py` (replace stub) — `ReportCounts`, `report`.
- `src/github/action.py` (create) — `run_action` (the entrypoint core, with injectable seams).
- `docsmith.py` (modify) — `github-action` subcommand + output writing.
- `action.yml` (modify), `Dockerfile` (modify) — packaging finalize.
- `README.md` (modify), `tests/integration/test_github_action_live.py` (create) — gated real-GitHub test + docs.

---

## Task 0: `auto_fix` setting

**Files:**
- Modify: `src/utils/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: existing `Settings` + `load_settings`.
- Produces: `Settings.auto_fix: bool` (default `True`), read from the top-level `auto_fix` YAML key.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_config.py`:

```python
def test_load_settings_reads_auto_fix_false(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("auto_fix: false\n")
    assert load_settings(str(cfg)).auto_fix is False


def test_load_settings_auto_fix_defaults_true(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("{}\n")
    assert load_settings(str(cfg)).auto_fix is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/unit/test_config.py -k auto_fix -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'auto_fix'`.

- [ ] **Step 3: Add the field + read it**

In `src/utils/config.py`, add to the `Settings` dataclass (after `repair_autofix_change_kinds`):

```python
    auto_fix: bool = True
```

and to the docstring Attributes:

```python
        auto_fix: Whether the reporter opens a companion fix-PR for AUTOFIX corrections.
```

In `load_settings`, after the `repair = raw.get("repair") or {}` line add:

```python
    auto_fix = raw.get("auto_fix", True)
    if auto_fix is None:
        auto_fix = True
```

and in the `Settings(...)` constructor add:

```python
        auto_fix=auto_fix,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/utils/config.py tests/unit/test_config.py
git commit -m "feat: add auto_fix setting"
```

---

## Task 1: `RepairResult.verified`

**Files:**
- Modify: `src/detection/models.py`
- Modify: `src/repair/engine.py`
- Test: `tests/integration/test_repair_verified.py`

**Interfaces:**
- Consumes: `repair_pr` (unchanged signature), the temp-repo fixture pattern from `tests/integration/test_repair_pr.py`.
- Produces: `RepairResult.verified: int` (default `0`), set by `repair_pr` to the count of investigator verdicts that were NOT stale.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_repair_verified.py` (reuse the temp-repo helpers from `tests/integration/test_repair_pr.py` — import them):

```python
from src.detection.models import RepairRoute  # noqa: F401
from src.llm.client import FakeLLMClient
from src.repair.engine import repair_pr
from src.utils.config import Settings
from tests.integration.test_repair_pr import _setup_repo


def _fresh_verdict_client() -> FakeLLMClient:
    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": "unused"}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        # staleness verdict: NOT stale
        return {"stale": False, "confidence": 0.2, "reason": "still accurate", "wrong_claims": []}

    return FakeLLMClient(respond)


def test_repair_pr_counts_verified_not_stale(tmp_path):
    repo, base, head, index_path = _setup_repo(tmp_path)
    result = repair_pr(str(repo), base, head, index_path, Settings(), _fresh_verdict_client())
    assert result.verified == 1        # the one suspect section was judged accurate
    assert result.outcomes == []       # nothing stale → nothing to repair
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_repair_verified.py -v`
Expected: FAIL — `RepairResult` has no attribute `verified` (or it is always 0).

- [ ] **Step 3: Add the field**

In `src/detection/models.py`, in the `RepairResult` dataclass add a field after `skipped`:

```python
    verified: int = 0
```

and to its docstring Attributes:

```python
        verified: Count of investigated sections the LLM judged still accurate (not stale).
```

- [ ] **Step 4: Populate it in `repair_pr`**

In `src/repair/engine.py`, inside `repair_pr`, immediately after the line
`stale = [v for v in inv_result.verdicts if v.stale]` add:

```python
    verified = sum(1 for v in inv_result.verdicts if not v.stale)
```

and change the `result = RepairResult()` line to:

```python
    result = RepairResult(verified=verified)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/integration/test_repair_verified.py -v`
Expected: PASS.

- [ ] **Step 6: Full suite check**

Run: `python3 -m pytest -q`
Expected: all prior tests still green + the new one (repair CLI unaffected — the new field defaults 0).

- [ ] **Step 7: Commit**

```bash
git add src/detection/models.py src/repair/engine.py tests/integration/test_repair_verified.py
git commit -m "feat: count verified-accurate sections in RepairResult"
```

---

## Task 2: PR context loader

**Files:**
- Create: `src/github/context.py`
- Test: `tests/unit/test_github_context.py`

**Interfaces:**
- Produces: `PRContext` (frozen: `repo: str`, `base_sha: str`, `head_sha: str`, `pr_number: int`, `head_ref: str`, `base_ref: str`) and `load_pr_context(env: Mapping[str, str]) -> PRContext`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_github_context.py`:

```python
import json

import pytest

from src.github.context import load_pr_context


def _write_event(tmp_path, payload) -> str:
    p = tmp_path / "event.json"
    p.write_text(json.dumps(payload))
    return str(p)


def test_load_pr_context_from_event(tmp_path):
    event = _write_event(
        tmp_path,
        {
            "number": 7,
            "pull_request": {
                "base": {"sha": "base123", "ref": "main"},
                "head": {"sha": "head456", "ref": "feature-x"},
            },
        },
    )
    env = {"GITHUB_REPOSITORY": "octo/repo", "GITHUB_EVENT_PATH": event}
    ctx = load_pr_context(env)
    assert ctx.repo == "octo/repo"
    assert ctx.base_sha == "base123"
    assert ctx.head_sha == "head456"
    assert ctx.pr_number == 7
    assert ctx.head_ref == "feature-x"
    assert ctx.base_ref == "main"


def test_load_pr_context_rejects_non_pr_event(tmp_path):
    event = _write_event(tmp_path, {"pushed": True})
    env = {"GITHUB_REPOSITORY": "octo/repo", "GITHUB_EVENT_PATH": event}
    with pytest.raises(ValueError, match="pull_request"):
        load_pr_context(env)


def test_load_pr_context_requires_env(tmp_path):
    with pytest.raises(ValueError):
        load_pr_context({})
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_github_context.py -v`
Expected: FAIL — `src.github.context` does not exist.

- [ ] **Step 3: Implement**

Create `src/github/context.py`:

```python
"""Load pull-request context from the GitHub Actions environment + event payload."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PRContext:
    """Identifying details of the pull request the Action is running on.

    Attributes:
        repo: Repository in ``"owner/name"`` form.
        base_sha: SHA of the PR's base (target) commit.
        head_sha: SHA of the PR's head (source) commit.
        pr_number: The pull request number.
        head_ref: The PR's head branch name.
        base_ref: The PR's base branch name.
    """

    repo: str
    base_sha: str
    head_sha: str
    pr_number: int
    head_ref: str
    base_ref: str


def load_pr_context(env: Mapping[str, str]) -> PRContext:
    """Build a PRContext from the Actions env vars and the event payload file.

    Args:
        env: Environment mapping (typically ``os.environ``) with ``GITHUB_REPOSITORY``
            and ``GITHUB_EVENT_PATH`` set.

    Returns:
        A populated PRContext.

    Raises:
        ValueError: If required env vars are missing or the event is not a
            ``pull_request`` payload.
    """
    repo = env.get("GITHUB_REPOSITORY")
    event_path = env.get("GITHUB_EVENT_PATH")
    if not repo or not event_path:
        raise ValueError("GITHUB_REPOSITORY and GITHUB_EVENT_PATH must be set")

    with open(event_path) as fh:
        event = json.load(fh)

    pr = event.get("pull_request")
    if pr is None:
        raise ValueError("not a pull_request event: 'pull_request' missing from event payload")

    return PRContext(
        repo=repo,
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        pr_number=event.get("number", pr.get("number")),
        head_ref=pr["head"]["ref"],
        base_ref=pr["base"]["ref"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_github_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/github/context.py tests/unit/test_github_context.py
git commit -m "feat: load PR context from the Actions event payload"
```

---

## Task 3: AUTOFIX file application

**Files:**
- Create: `src/github/apply.py`
- Test: `tests/unit/test_github_apply.py`

**Interfaces:**
- Consumes: `RepairOutcome`/`RepairRoute` (`src/detection/models.py`), `Index` (`src/models.py`), `DocSection` (has `file`, `start_line`, `end_line`).
- Produces: `apply_corrections(outcomes: list[RepairOutcome], index: Index, read_file: Callable[[str], str]) -> dict[str, str]` — new full content per doc file, AUTOFIX outcomes only.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_github_apply.py`:

```python
from src.detection.models import RepairOutcome, RepairProposal, RepairRoute, ValidationResult
from src.github.apply import apply_corrections
from src.models import DocSection, Index

CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")


def _section(sid, start, end):
    return DocSection(
        id=sid, heading_path=("H",), file="README.md", raw="x",
        start_line=start, end_line=end, referenced_symbols=(), referenced_config_keys=(),
    )


def _autofix(sid, revised):
    proposal = RepairProposal(
        symbol_id="app.py::f", section_id=sid, file="README.md",
        original_text="old", revised_text=revised, diff="(d)", changed=True,
    )
    return RepairOutcome(proposal=proposal, validation=CLEAN, route=RepairRoute.AUTOFIX, reason="ok")


def test_apply_replaces_section_span():
    index = Index(sections={"README.md#a": _section("README.md#a", 2, 2)})
    original = "line1\nOLD\nline3\n"
    files = apply_corrections([_autofix("README.md#a", "NEW")], index, lambda p: original)
    assert files == {"README.md": "line1\nNEW\nline3\n"}


def test_apply_multiple_edits_bottom_up_no_drift():
    index = Index(
        sections={
            "README.md#a": _section("README.md#a", 1, 1),
            "README.md#b": _section("README.md#b", 3, 3),
        }
    )
    original = "A\nmid\nB\n"
    outcomes = [_autofix("README.md#a", "A2\nA3"), _autofix("README.md#b", "B2")]
    files = apply_corrections(outcomes, index, lambda p: original)
    # #b (line 3) applied first, then #a (line 1); no line drift
    assert files == {"README.md": "A2\nA3\nmid\nB2\n"}


def test_apply_ignores_non_autofix_and_missing_sections():
    index = Index(sections={})
    files = apply_corrections([_autofix("README.md#gone", "NEW")], index, lambda p: "x\n")
    assert files == {}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_github_apply.py -v`
Expected: FAIL — `src.github.apply` does not exist.

- [ ] **Step 3: Implement**

Create `src/github/apply.py`:

```python
"""Apply AUTOFIX corrections into doc-file content (deterministic span-replace)."""

from __future__ import annotations

from collections.abc import Callable

from src.detection.models import RepairOutcome, RepairRoute
from src.models import Index
```

Then the function:

```python
def apply_corrections(
    outcomes: list[RepairOutcome],
    index: Index,
    read_file: Callable[[str], str],
) -> dict[str, str]:
    """Produce corrected file content for each doc file touched by an AUTOFIX outcome.

    Args:
        outcomes: All repair outcomes; only AUTOFIX ones are applied.
        index: The current index, for each section's line span.
        read_file: Reads a doc file's current content by repo-relative path.

    Returns:
        A mapping of doc-file path to its new full content. Files with no applicable
        AUTOFIX edit are absent. Multiple edits to one file are applied bottom-up so
        earlier edits do not shift later line numbers; the file's trailing newline is
        preserved.
    """
    by_file: dict[str, list] = {}
    for outcome in outcomes:
        if outcome.route is not RepairRoute.AUTOFIX:
            continue
        section = index.sections.get(outcome.proposal.section_id)
        if section is None:
            continue
        by_file.setdefault(section.file, []).append((section, outcome.proposal))

    result: dict[str, str] = {}
    for file, edits in by_file.items():
        original = read_file(file)
        lines = original.splitlines()
        for section, proposal in sorted(edits, key=lambda e: e[0].start_line, reverse=True):
            lines[section.start_line - 1 : section.end_line] = proposal.revised_text.splitlines()
        trailing = "\n" if original.endswith("\n") else ""
        result[file] = "\n".join(lines) + trailing

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_github_apply.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/github/apply.py tests/unit/test_github_apply.py
git commit -m "feat: apply AUTOFIX corrections into doc-file content"
```

---

## Task 4: Summary markdown

**Files:**
- Create: `src/github/summary.py`
- Test: `tests/unit/test_github_summary.py`

**Interfaces:**
- Consumes: `RepairResult`/`RepairRoute` (`src/detection/models.py`).
- Produces: `MARKER = "<!-- docsmith:summary -->"` and `build_summary(result: RepairResult, fix_pr_url: str | None, auto_fix: bool) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_github_summary.py`:

```python
from src.detection.models import (
    RepairOutcome, RepairProposal, RepairResult, RepairRoute, ValidationResult,
)
from src.github.summary import MARKER, build_summary

CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")


def _outcome(route, sid, diff="", reason="because"):
    proposal = RepairProposal(
        symbol_id="app.py::f", section_id=sid, file="README.md",
        original_text="old", revised_text="new", diff=diff, changed=True,
    )
    return RepairOutcome(proposal=proposal, validation=CLEAN, route=route, reason=reason)


def test_summary_has_marker_headline_and_sections():
    result = RepairResult(
        outcomes=[
            _outcome(RepairRoute.AUTOFIX, "README.md#users", reason="signature_changed"),
            _outcome(RepairRoute.FLAG, "README.md#config", diff="-old\n+new", reason="body_changed"),
        ],
        verified=3,
    )
    body = build_summary(result, "https://github.com/o/r/pull/42", auto_fix=True)
    assert body.startswith(MARKER)
    assert "3 verified" in body
    assert "1 auto-fixed" in body
    assert "https://github.com/o/r/pull/42" in body
    assert "1 flagged" in body
    assert "README.md#users" in body
    assert "README.md#config" in body
    assert "<details>" in body and "```diff" in body and "-old" in body
    assert "merge" not in body.lower() or "never" in body.lower()  # never implies auto-merge


def test_summary_autofix_disabled_labels_proposed():
    result = RepairResult(outcomes=[_outcome(RepairRoute.AUTOFIX, "README.md#x")], verified=0)
    body = build_summary(result, None, auto_fix=False)
    assert "Proposed" in body            # not opened as a PR
    assert "0 verified" in body
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_github_summary.py -v`
Expected: FAIL — `src.github.summary` does not exist.

- [ ] **Step 3: Implement**

Create `src/github/summary.py`:

```python
"""Build the Docsmith pull-request summary comment (markdown)."""

from __future__ import annotations

from src.detection.models import RepairResult, RepairRoute

MARKER = "<!-- docsmith:summary -->"


def build_summary(result: RepairResult, fix_pr_url: str | None, auto_fix: bool) -> str:
    """Render the summary comment body.

    Args:
        result: The repair result being reported.
        fix_pr_url: URL of the companion fix-PR, or None when none was opened.
        auto_fix: Whether auto-fix is enabled (controls the AUTOFIX section heading).

    Returns:
        A markdown string beginning with the hidden idempotency marker.
    """
    autofix = [o for o in result.outcomes if o.route is RepairRoute.AUTOFIX]
    flag = [o for o in result.outcomes if o.route is RepairRoute.FLAG]

    fixed_txt = f"{len(autofix)} auto-fixed"
    if fix_pr_url:
        fixed_txt += f" ([fix PR]({fix_pr_url}))"

    lines: list[str] = [
        MARKER,
        "",
        f"**Docsmith:** {result.verified} verified · {fixed_txt} · {len(flag)} flagged",
        "",
    ]

    if autofix:
        opened = auto_fix and fix_pr_url is not None
        lines.append("### Auto-fixed" if opened else "### Proposed fixes (auto-fix disabled)")
        for outcome in autofix:
            lines.append(f"- `{outcome.proposal.section_id}` — {outcome.reason}")
        lines.append("")

    if flag:
        lines.append("### Needs review")
        for outcome in flag:
            lines.append(f"- `{outcome.proposal.section_id}` — {outcome.reason}")
            lines.append("")
            lines.append("<details><summary>Proposed correction</summary>")
            lines.append("")
            lines.append("```diff")
            lines.append(outcome.proposal.diff)
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    skipped = sum(result.skipped.values())
    if skipped:
        lines.append(f"_{skipped} section(s) skipped due to malformed model output._")

    lines.append("")
    lines.append("_Docsmith never auto-merges — review and merge if correct._")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_github_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/github/summary.py tests/unit/test_github_summary.py
git commit -m "feat: build the PR summary comment markdown"
```

---

## Task 5: `GitHubClient` seam + fake

**Files:**
- Modify (replace stub): `src/github/client.py`
- Test: `tests/unit/test_github_client_fake.py`

**Interfaces:**
- Produces: `GitHubClient` (`@runtime_checkable Protocol`) with `upsert_summary_comment(pr_number: int, body: str) -> None` and `open_or_update_fix_pr(head_ref: str, base_ref: str, branch: str, files: dict[str, str], title: str, body: str) -> str`; and `FakeGitHubClient`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_github_client_fake.py`:

```python
from src.github.client import FakeGitHubClient, GitHubClient


def test_fake_is_a_github_client():
    assert isinstance(FakeGitHubClient(), GitHubClient)


def test_fake_records_comment_upsert_last_wins():
    c = FakeGitHubClient()
    c.upsert_summary_comment(7, "first")
    c.upsert_summary_comment(7, "second")
    assert c.comments[7] == "second"     # upsert overwrites
    assert c.comment_calls == 2          # but was called twice


def test_fake_records_fix_pr_and_returns_url():
    c = FakeGitHubClient(fix_pr_url="https://github.com/o/r/pull/5")
    url = c.open_or_update_fix_pr("head", "main", "docsmith/fix-pr-7", {"README.md": "new"}, "t", "b")
    assert url == "https://github.com/o/r/pull/5"
    assert c.fix_prs[0]["branch"] == "docsmith/fix-pr-7"
    assert c.fix_prs[0]["files"] == {"README.md": "new"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_github_client_fake.py -v`
Expected: FAIL — `FakeGitHubClient` not importable (stub has no such class).

- [ ] **Step 3: Implement (replace the stub)**

Replace the entire contents of `src/github/client.py` with:

```python
"""GitHub write-side seam: summary comment + companion fix-PR.

The protocol has a scripted ``FakeGitHubClient`` for offline tests and a real
``PyGithubClient`` that lazy-imports PyGithub (so importing this module needs no
SDK, token, or network). ``PyGithubClient`` is added in a later task.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GitHubClient(Protocol):
    """Write-side operations Docsmith performs on a pull request."""

    def upsert_summary_comment(self, pr_number: int, body: str) -> None: ...

    def open_or_update_fix_pr(
        self,
        head_ref: str,
        base_ref: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str: ...


class FakeGitHubClient:
    """Offline, scripted GitHubClient for tests: records calls, returns a canned URL."""

    def __init__(self, fix_pr_url: str = "https://github.com/fake/repo/pull/999") -> None:
        self._fix_pr_url = fix_pr_url
        self.comments: dict[int, str] = {}
        self.comment_calls = 0
        self.fix_prs: list[dict] = []

    def upsert_summary_comment(self, pr_number: int, body: str) -> None:
        self.comments[pr_number] = body
        self.comment_calls += 1

    def open_or_update_fix_pr(
        self,
        head_ref: str,
        base_ref: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str:
        self.fix_prs.append(
            {
                "head_ref": head_ref,
                "base_ref": base_ref,
                "branch": branch,
                "files": files,
                "title": title,
                "body": body,
            }
        )
        return self._fix_pr_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_github_client_fake.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/github/client.py tests/unit/test_github_client_fake.py
git commit -m "feat: GitHubClient seam and fake"
```

---

## Task 6: `PyGithubClient` (real backend)

**Files:**
- Modify: `src/github/client.py`
- Test: `tests/unit/test_github_client_pygithub.py`

**Interfaces:**
- Consumes: `MARKER` (`src/github/summary.py`), the `GitHubClient` protocol.
- Produces: `PyGithubClient(repo: str, token: str)` implementing `GitHubClient`; lazy-imports `github` inside a `_repo()` seam.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_github_client_pygithub.py`:

```python
import sys
from unittest.mock import MagicMock

import github  # PyGithub is installed; used to raise the not-found exception

from src.github.client import PyGithubClient
from src.github.summary import MARKER


def test_importing_client_module_does_not_import_pygithub():
    sys.modules.pop("github", None)
    sys.modules.pop("src.github.client", None)
    import src.github.client  # noqa: F401
    assert "github" not in sys.modules  # lazy: only imported inside methods


def test_upsert_edits_existing_marker_comment(monkeypatch):
    repo = MagicMock()
    existing = MagicMock()
    existing.body = f"{MARKER}\nold summary"
    pr = repo.get_pull.return_value
    pr.get_issue_comments.return_value = [existing]
    client = PyGithubClient("o/r", "tok")
    monkeypatch.setattr(client, "_repo", lambda: repo)

    client.upsert_summary_comment(7, "new body")

    existing.edit.assert_called_once_with("new body")
    pr.create_issue_comment.assert_not_called()


def test_upsert_creates_when_no_marker(monkeypatch):
    repo = MagicMock()
    pr = repo.get_pull.return_value
    pr.get_issue_comments.return_value = []
    client = PyGithubClient("o/r", "tok")
    monkeypatch.setattr(client, "_repo", lambda: repo)

    client.upsert_summary_comment(7, "new body")

    pr.create_issue_comment.assert_called_once_with("new body")


def test_open_fix_pr_force_updates_branch_and_creates_pr(monkeypatch):
    repo = MagicMock()
    repo.get_branch.return_value.commit.sha = "headsha"
    # branch ref does not exist yet → get_git_ref raises → create_git_ref
    repo.get_git_ref.side_effect = github.GithubException(404, "nf", None)
    # file does not exist → get_contents raises → create_file
    repo.get_contents.side_effect = github.GithubException(404, "nf", None)
    repo.get_pulls.return_value = []
    repo.create_pull.return_value.html_url = "https://github.com/o/r/pull/12"
    client = PyGithubClient("o/r", "tok")
    monkeypatch.setattr(client, "_repo", lambda: repo)

    url = client.open_or_update_fix_pr(
        "feature", "main", "docsmith/fix-pr-7", {"README.md": "new"}, "title", "body"
    )

    assert url == "https://github.com/o/r/pull/12"
    repo.create_git_ref.assert_called_once()
    repo.create_file.assert_called_once()
    repo.create_pull.assert_called_once()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_github_client_pygithub.py -v`
Expected: FAIL — `PyGithubClient` not importable.

- [ ] **Step 3: Implement (append to `src/github/client.py`)**

Add `from src.github.summary import MARKER` under the existing imports, then append:

```python
class PyGithubClient:
    """Real GitHubClient backed by PyGithub. Lazy-imports ``github`` inside methods."""

    def __init__(self, repo: str, token: str) -> None:
        self._repo_name = repo
        self._token = token
        self._repo_handle = None

    def _repo(self):  # noqa: ANN202 - PyGithub Repository type is not imported at module scope
        """Return a cached PyGithub Repository handle, importing the SDK lazily."""
        if self._repo_handle is None:
            import github

            self._repo_handle = github.Github(self._token).get_repo(self._repo_name)
        return self._repo_handle

    def upsert_summary_comment(self, pr_number: int, body: str) -> None:
        """Edit Docsmith's existing summary comment if present, else create it."""
        pr = self._repo().get_pull(pr_number)
        for comment in pr.get_issue_comments():
            if MARKER in comment.body:
                comment.edit(body)
                return
        pr.create_issue_comment(body)

    def open_or_update_fix_pr(
        self,
        head_ref: str,
        base_ref: str,
        branch: str,
        files: dict[str, str],
        title: str,
        body: str,
    ) -> str:
        """Force-update the fix branch off head, commit files, open/update the PR."""
        import github

        repo = self._repo()
        head_sha = repo.get_branch(head_ref).commit.sha

        try:
            ref = repo.get_git_ref(f"heads/{branch}")
            ref.edit(head_sha, force=True)
        except github.GithubException:
            repo.create_git_ref(f"refs/heads/{branch}", head_sha)

        for path, content in files.items():
            try:
                existing = repo.get_contents(path, ref=branch)
                repo.update_file(path, f"docs: update {path}", content, existing.sha, branch=branch)
            except github.GithubException:
                repo.create_file(path, f"docs: create {path}", content, branch=branch)

        owner = self._repo_name.split("/")[0]
        pulls = list(repo.get_pulls(state="open", head=f"{owner}:{branch}", base=base_ref))
        if pulls:
            pulls[0].edit(title=title, body=body)
            return pulls[0].html_url
        return repo.create_pull(title=title, body=body, base=base_ref, head=branch).html_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_github_client_pygithub.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/github/client.py tests/unit/test_github_client_pygithub.py
git commit -m "feat: real PyGithub-backed GitHub client"
```

---

## Task 7: Reporter

**Files:**
- Modify (replace stub): `src/github/reporter.py`
- Test: `tests/unit/test_github_reporter.py`

**Interfaces:**
- Consumes: `apply_corrections`, `build_summary`, `GitHubClient`, `PRContext`, `RepairResult`/`RepairRoute`, `Settings`, `Index`.
- Produces: `ReportCounts` (frozen: `verified: int`, `fixed: int`, `flagged: int`, `fix_pr_url: str | None`) and `report(result, pr_context, settings, client, index, read_file) -> ReportCounts`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_github_reporter.py`:

```python
from src.detection.models import (
    RepairOutcome, RepairProposal, RepairResult, RepairRoute, ValidationResult,
)
from src.github.client import FakeGitHubClient
from src.github.context import PRContext
from src.github.reporter import report
from src.github.summary import MARKER
from src.models import DocSection, Index
from src.utils.config import Settings

CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")
CTX = PRContext(
    repo="o/r", base_sha="b", head_sha="h", pr_number=7, head_ref="feature", base_ref="main"
)


def _index():
    section = DocSection(
        id="README.md#users", heading_path=("Users",), file="README.md", raw="x",
        start_line=1, end_line=1, referenced_symbols=(), referenced_config_keys=(),
    )
    return Index(sections={"README.md#users": section})


def _autofix():
    proposal = RepairProposal(
        symbol_id="app.py::create_user", section_id="README.md#users", file="README.md",
        original_text="old", revised_text="NEW", diff="-old\n+NEW", changed=True,
    )
    return RepairOutcome(proposal=proposal, validation=CLEAN, route=RepairRoute.AUTOFIX, reason="signature_changed")


def test_report_opens_fix_pr_and_upserts_comment():
    result = RepairResult(outcomes=[_autofix()], verified=2)
    gh = FakeGitHubClient(fix_pr_url="https://github.com/o/r/pull/12")
    counts = report(result, CTX, Settings(), gh, _index(), lambda p: "old\n")
    assert counts.fixed == 1 and counts.verified == 2 and counts.flagged == 0
    assert counts.fix_pr_url == "https://github.com/o/r/pull/12"
    assert gh.fix_prs[0]["branch"] == "docsmith/fix-pr-7"
    assert gh.fix_prs[0]["files"] == {"README.md": "NEW\n"}
    assert MARKER in gh.comments[7] and "https://github.com/o/r/pull/12" in gh.comments[7]


def test_report_auto_fix_disabled_opens_no_pr():
    result = RepairResult(outcomes=[_autofix()], verified=0)
    gh = FakeGitHubClient()
    settings = Settings(auto_fix=False)
    counts = report(result, CTX, settings, gh, _index(), lambda p: "old\n")
    assert counts.fixed == 1              # counted as an autofix candidate
    assert counts.fix_pr_url is None
    assert gh.fix_prs == []                # but no PR opened
    assert MARKER in gh.comments[7]


def test_report_is_idempotent_reuses_branch_and_comment():
    result = RepairResult(outcomes=[_autofix()], verified=0)
    gh = FakeGitHubClient()
    report(result, CTX, Settings(), gh, _index(), lambda p: "old\n")
    report(result, CTX, Settings(), gh, _index(), lambda p: "old\n")
    assert gh.comment_calls == 2                       # called twice
    assert len(gh.comments) == 1                       # one comment (last wins)
    assert {c["branch"] for c in gh.fix_prs} == {"docsmith/fix-pr-7"}  # same branch reused
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_github_reporter.py -v`
Expected: FAIL — `report` not importable (stub).

- [ ] **Step 3: Implement (replace the stub)**

Replace the entire contents of `src/github/reporter.py` with:

```python
"""Stage 9: post the summary comment and open/update the companion fix-PR. Never merges."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.detection.models import RepairResult, RepairRoute
from src.github.apply import apply_corrections
from src.github.client import GitHubClient
from src.github.context import PRContext
from src.github.summary import build_summary
from src.models import Index
from src.utils.config import Settings


@dataclass(frozen=True)
class ReportCounts:
    """Counts written to the Action's outputs.

    Attributes:
        verified: Sections confirmed still accurate.
        fixed: AUTOFIX corrections (opened in the fix-PR when auto-fix is on).
        flagged: Sections flagged for human review.
        fix_pr_url: URL of the companion fix-PR, or None if none was opened.
    """

    verified: int
    fixed: int
    flagged: int
    fix_pr_url: str | None


def report(
    result: RepairResult,
    pr_context: PRContext,
    settings: Settings,
    client: GitHubClient,
    index: Index,
    read_file: Callable[[str], str],
) -> ReportCounts:
    """Open/update the companion fix-PR (if enabled) and upsert the summary comment.

    Args:
        result: The repair result to report.
        pr_context: The pull request being reported on.
        settings: Configuration (``auto_fix`` gates opening the fix-PR).
        client: The GitHub write-side client.
        index: The current index, for AUTOFIX section spans.
        read_file: Reads a doc file's current content by repo-relative path.

    Returns:
        A ReportCounts summarising what was reported.

    Raises:
        RuntimeError: If a GitHub API call fails (propagated from the client).
    """
    autofix = [o for o in result.outcomes if o.route is RepairRoute.AUTOFIX]
    flag = [o for o in result.outcomes if o.route is RepairRoute.FLAG]

    fix_pr_url: str | None = None
    if settings.auto_fix and autofix:
        files = apply_corrections(result.outcomes, index, read_file)
        if files:
            branch = f"docsmith/fix-pr-{pr_context.pr_number}"
            title = f"docs: sync documentation for #{pr_context.pr_number}"
            body = (
                f"Automated documentation corrections for #{pr_context.pr_number}.\n\n"
                "Review and merge if correct. Docsmith never auto-merges."
            )
            fix_pr_url = client.open_or_update_fix_pr(
                pr_context.head_ref, pr_context.base_ref, branch, files, title, body
            )

    summary = build_summary(result, fix_pr_url, settings.auto_fix)
    client.upsert_summary_comment(pr_context.pr_number, summary)

    return ReportCounts(
        verified=result.verified, fixed=len(autofix), flagged=len(flag), fix_pr_url=fix_pr_url
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_github_reporter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/github/reporter.py tests/unit/test_github_reporter.py
git commit -m "feat: reporter posts summary comment and companion fix-PR"
```

---

## Task 8: Action entrypoint

**Files:**
- Create: `src/github/action.py`
- Modify: `docsmith.py`
- Test: `tests/integration/test_github_action.py`

**Interfaces:**
- Consumes: `load_pr_context`, `report`/`ReportCounts`, `make_client` (`src/detection/investigator.py`), `repair_pr`, `build_index`, `load_index`, `load_settings`/`Settings`, `PyGithubClient`.
- Produces: `run_action(env, repo_root, *, embeddings=True, llm_client=None, gh_client=None) -> ReportCounts`; a `github-action` CLI subcommand that calls it and writes `$GITHUB_OUTPUT`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_github_action.py`. Reuse the temp-repo helpers from `tests/integration/test_repair_pr.py` (`_setup_repo` builds a repo whose README references a documented symbol and whose head commit changes that symbol's signature).

```python
import json

from src.github.action import run_action
from src.github.client import FakeGitHubClient
from src.llm.client import FakeLLMClient
from src.github.summary import MARKER
from tests.integration.test_repair_pr import _setup_repo


def _pipeline_client() -> FakeLLMClient:
    corrected = "Use `create_user(name, email)` to make a user."

    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": corrected}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        return {
            "stale": True, "confidence": 0.9,
            "reason": "create_user now takes an email argument",
            "wrong_claims": ["create_user(name)"],
        }

    return FakeLLMClient(respond)


def _event(tmp_path, base_sha, head_sha) -> str:
    payload = {
        "number": 7,
        "pull_request": {
            "base": {"sha": base_sha, "ref": "main"},
            "head": {"sha": head_sha, "ref": "feature"},
        },
    }
    p = tmp_path / "event.json"
    p.write_text(json.dumps(payload))
    return str(p)


def test_run_action_reports_autofix(tmp_path):
    repo, base, head, _index_path = _setup_repo(tmp_path)
    env = {
        "GITHUB_REPOSITORY": "octo/repo",
        "GITHUB_EVENT_PATH": _event(tmp_path, base, head),
        "INPUT_LLM-BACKEND": "fake",
    }
    gh = FakeGitHubClient(fix_pr_url="https://github.com/octo/repo/pull/50")
    counts = run_action(
        env, str(repo), embeddings=False, llm_client=_pipeline_client(), gh_client=gh
    )
    assert counts.fixed == 1
    assert counts.fix_pr_url == "https://github.com/octo/repo/pull/50"
    assert gh.fix_prs[0]["branch"] == "docsmith/fix-pr-7"
    assert "create_user(name, email)" in gh.fix_prs[0]["files"]["README.md"]
    assert MARKER in gh.comments[7] and "auto-fixed" in gh.comments[7]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_github_action.py -v`
Expected: FAIL — `src.github.action` does not exist.

- [ ] **Step 3: Implement `run_action`**

Create `src/github/action.py`:

```python
"""GitHub Action entrypoint core: env → settings → index → repair → report."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from src.detection.investigator import make_client
from src.github.action_settings import settings_from_env
from src.github.client import PyGithubClient
from src.github.context import load_pr_context
from src.github.reporter import ReportCounts, report
from src.index.builder import build_index
from src.index.store import load_index
from src.repair.engine import repair_pr


def run_action(
    env: Mapping[str, str],
    repo_root: str,
    *,
    embeddings: bool = True,
    llm_client=None,
    gh_client=None,
) -> ReportCounts:
    """Run the full Action pipeline for one pull request.

    Args:
        env: Environment mapping (``os.environ`` in production).
        repo_root: Path to the checked-out repository.
        embeddings: Whether to build the index with embeddings (True in production;
            tests pass False to stay offline).
        llm_client: Optional LLM client override (tests inject a FakeLLMClient).
        gh_client: Optional GitHub client override (tests inject a FakeGitHubClient).

    Returns:
        A ReportCounts for the run.

    Raises:
        RuntimeError: If the LLM backend is unavailable or a GitHub API call fails.
    """
    settings = settings_from_env(env)
    pr = load_pr_context(env)

    index_path = os.path.join(repo_root, ".docsmith", "index.json")
    build_index(repo_root, output_path=index_path, embeddings=embeddings, full=True)
    index = load_index(index_path)

    llm = llm_client or make_client(settings)
    result = repair_pr(repo_root, pr.base_sha, pr.head_sha, index_path, settings, llm)

    if gh_client is None:
        token = env.get("INPUT_GITHUB-TOKEN") or env.get("GITHUB_TOKEN") or ""
        gh_client = PyGithubClient(pr.repo, token)

    def read_file(path: str) -> str:
        return (Path(repo_root) / path).read_text()

    return report(result, pr, settings, gh_client, index, read_file)
```

- [ ] **Step 4: Implement the env→Settings merge**

Create `src/github/action_settings.py`:

```python
"""Merge GitHub Action inputs (INPUT_* env vars) into a Settings object."""

from __future__ import annotations

from collections.abc import Mapping

from src.utils.config import Settings, load_settings


def settings_from_env(env: Mapping[str, str]) -> Settings:
    """Build Settings from a base config plus GitHub Action input env vars.

    Reads ``INPUT_LLM-BACKEND``, ``INPUT_OLLAMA-HOST``, ``INPUT_CONFIDENCE-THRESHOLD``,
    ``INPUT_AUTO-FIX``, and ``INPUT_IGNORE-GLOBS`` when present, overriding the base
    config. (``doc-globs`` is accepted by the Action but not yet consumed by index
    discovery.)

    Args:
        env: Environment mapping with Action inputs.

    Returns:
        A populated Settings.
    """
    settings = load_settings(env.get("INPUT_CONFIG") or "configs/base.yaml")

    backend = env.get("INPUT_LLM-BACKEND")
    if backend:
        settings.llm_backend = backend

    host = env.get("INPUT_OLLAMA-HOST")
    if host:
        settings.ollama_host = host

    threshold = env.get("INPUT_CONFIDENCE-THRESHOLD")
    if threshold:
        settings.repair_confidence_threshold = float(threshold)

    auto_fix = env.get("INPUT_AUTO-FIX")
    if auto_fix not in (None, ""):
        settings.auto_fix = auto_fix.strip().lower() == "true"

    ignore = env.get("INPUT_IGNORE-GLOBS")
    if ignore:
        settings.doc_ignore = [g.strip() for g in ignore.split(",") if g.strip()]

    return settings
```

> Fix the `run_action` import to match: `from src.github.action_settings import settings_from_env`.

- [ ] **Step 5: Run the integration test to verify it passes**

Run: `python3 -m pytest tests/integration/test_github_action.py -v`
Expected: PASS.

- [ ] **Step 6: Add the `github-action` subcommand + output writing (`docsmith.py`)**

Add imports near the top of `docsmith.py`:

```python
from src.github.action import run_action
```

After the `repair` subparser block (before `args = parser.parse_args()`), add:

```python
    action_parser = subparsers.add_parser(
        "github-action",
        help="Run Docsmith as a GitHub Action on the current pull request.",
    )
    action_parser.add_argument(
        "--repo",
        default=".",
        help="Path to the checked-out repository (default: current directory).",
    )
```

After the `elif args.subcommand == "repair":` block, add:

```python
    elif args.subcommand == "github-action":
        counts = run_action(os.environ, args.repo)
        output_path = os.environ.get("GITHUB_OUTPUT")
        lines = [
            f"verified={counts.verified}",
            f"fixed={counts.fixed}",
            f"flagged={counts.flagged}",
            f"fix-pr-url={counts.fix_pr_url or ''}",
        ]
        if output_path:
            with open(output_path, "a") as fh:
                fh.write("\n".join(lines) + "\n")
        print(
            f"Docsmith: {counts.verified} verified, {counts.fixed} auto-fixed, "
            f"{counts.flagged} flagged"
        )
```

- [ ] **Step 7: Write a test for the CLI output writing**

Add to `tests/integration/test_github_action.py`:

```python
def test_github_action_cli_writes_outputs(tmp_path, monkeypatch):
    import docsmith
    from src.github.reporter import ReportCounts

    out = tmp_path / "gh_output"
    out.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(
        docsmith, "run_action",
        lambda env, repo: ReportCounts(verified=2, fixed=1, flagged=3, fix_pr_url="u"),
    )
    monkeypatch.setattr("sys.argv", ["docsmith", "github-action", "--repo", str(tmp_path)])
    docsmith.main()
    text = out.read_text()
    assert "verified=2" in text and "fixed=1" in text and "flagged=3" in text
    assert "fix-pr-url=u" in text
```

- [ ] **Step 8: Run tests + full suite + ruff**

Run: `python3 -m pytest tests/integration/test_github_action.py -v && python3 -m pytest -q && python3 -m ruff check src/github docsmith.py`
Expected: all green; ruff clean.

- [ ] **Step 9: Commit**

```bash
git add src/github/action.py src/github/action_settings.py docsmith.py tests/integration/test_github_action.py
git commit -m "feat: github-action entrypoint wiring inputs to reporter"
```

---

## Task 9: Finalize `action.yml` + `Dockerfile`

**Files:**
- Modify: `action.yml`
- Modify: `Dockerfile`
- Test: `tests/unit/test_action_yml.py`

**Interfaces:**
- Consumes: nothing in code; the entrypoint reads the `INPUT_*` env vars these inputs produce.
- Produces: an `action.yml` with an optional Claude key + `llm-backend`/`ollama-host` inputs + `fix-pr-url` output; a `Dockerfile` that bakes in the embedding model and uses the `github-action` subcommand.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_action_yml.py`:

```python
import yaml


def _action():
    with open("action.yml") as fh:
        return yaml.safe_load(fh)


def test_anthropic_key_is_optional():
    assert _action()["inputs"]["anthropic-api-key"]["required"] is False


def test_llm_backend_and_ollama_host_inputs_present():
    inputs = _action()["inputs"]
    assert inputs["llm-backend"]["default"] == "ollama"
    assert "ollama-host" in inputs


def test_outputs_include_counts_and_fix_pr_url():
    outputs = _action()["outputs"]
    for key in ("verified", "fixed", "flagged", "fix-pr-url"):
        assert key in outputs
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_action_yml.py -v`
Expected: FAIL — `anthropic-api-key` is currently `required: true`; `llm-backend`/`ollama-host`/`fix-pr-url` absent.

- [ ] **Step 3: Edit `action.yml`**

In `action.yml`: change `anthropic-api-key` to `required: false` (remove the line `required: true`, add `required: false`; keep the description). Under `inputs:` add:

```yaml
  llm-backend:
    description: "LLM backend: ollama (free, local — default), claude (needs anthropic-api-key), or fake."
    required: false
    default: "ollama"
  ollama-host:
    description: "Base URL of the Ollama server (reachable from the Action container)."
    required: false
    default: "http://host.docker.internal:11434"
```

Under `outputs:` add:

```yaml
  fix-pr-url:
    description: "URL of the companion fix-PR opened for high-confidence corrections, if any."
```

- [ ] **Step 4: Edit `Dockerfile`**

Replace the model-warm TODO comment block with a real pre-download, and change the entrypoint to the `github-action` subcommand:

```dockerfile
# Pre-download the local embedding model into the image layer.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY . .

ENTRYPOINT ["python", "/app/docsmith.py", "github-action"]
```

(Remove the old `ENTRYPOINT ["python", "/app/docsmith.py", "--github-action"]` line.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/unit/test_action_yml.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add action.yml Dockerfile tests/unit/test_action_yml.py
git commit -m "feat: finalize action.yml and Dockerfile for the Action"
```

---

## Task 10: Gated real-GitHub test + README

**Files:**
- Create: `tests/integration/test_github_live.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `PyGithubClient`.

- [ ] **Step 1: Write the gated test (collectable, skips cleanly)**

Create `tests/integration/test_github_live.py`:

```python
import os

import pytest

from src.github.client import PyGithubClient
from src.github.summary import MARKER

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_GITHUB_TESTS") != "1",
    reason="set DOCSMITH_RUN_GITHUB_TESTS=1 (with a token + test repo) to run the live GitHub test",
)


def test_upsert_summary_comment_on_real_pr():
    repo = os.environ["DOCSMITH_GITHUB_TEST_REPO"]      # e.g. "you/docsmith-sandbox"
    pr_number = int(os.environ["DOCSMITH_GITHUB_TEST_PR"])
    token = os.environ["GITHUB_TOKEN"]
    client = PyGithubClient(repo, token)
    client.upsert_summary_comment(pr_number, f"{MARKER}\nDocsmith live test — safe to delete.")
    # A second upsert must not create a duplicate (idempotency); no exception == pass.
    client.upsert_summary_comment(pr_number, f"{MARKER}\nDocsmith live test — updated.")
```

- [ ] **Step 2: Run to verify it SKIPS cleanly**

Run: `python3 -m pytest tests/integration/test_github_live.py -rs -v`
Expected: `1 skipped` with the reason shown; no collection error.

- [ ] **Step 3: Add the README section**

In `README.md`, add a section documenting the live run (adjust surrounding placement to fit the existing structure):

```markdown
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
```

- [ ] **Step 4: Run the gated test + full suite + ruff**

Run: `python3 -m pytest tests/integration/test_github_live.py -rs -v && python3 -m pytest -q && python3 -m ruff check .`
Expected: the live test SKIPPED; full suite green; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_github_live.py README.md
git commit -m "feat: gated live-GitHub test and real-PR run docs"
```

---

## Definition of Done (from the spec)

- On a real PR, the Action posts a summary comment, opens **one** companion fix-PR for AUTOFIX corrections (when `auto-fix` is on), and lists FLAG items with proposed diffs — at **$0** on Ollama + `github.token`, **never auto-merging**.
- `GitHubClient` seam with `PyGithubClient` + `FakeGitHubClient`; importing modules needs no SDK/token/network (asserted by a unit test).
- Re-runs update the same comment and fix-PR rather than duplicating.
- `action.yml` makes the Claude key optional and adds `llm-backend`/`ollama-host`; the `Dockerfile` bakes in the embedding model and uses the `github-action` subcommand.
- Default `pytest` suite fully offline ($0) and green; `ruff check .` clean.
- The gated real-GitHub test exists and skips cleanly in CI; the "run on a real fork" demo is documented.
- No LLM/AI attribution in any commit; living docs updated by the controller, not task implementers.
