# Evaluation & Polish (Week 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure Docsmith with reproducible numbers — a bundled curated corpus (headline detection precision/recall/F1 + secondary correction quality) and a real history-replay mining harness — and publish a metrics table to the README, all at $0 on local Ollama.

**Architecture:** Cases are file-pairs (`base_files`/`head_files` dicts) + gold labels; a materializer turns each into a scratch two-commit git repo so the existing `run_detection`/`investigate_pr`/`repair_pr` pipeline runs unchanged. A pure scoring core computes metrics; a runner replays cases through the pipeline; a mining harness synthesizes cases from a real repo's coupled code+doc commits; a `docsmith evaluate` CLI + `report.py` produce and publish the numbers.

**Tech Stack:** Python 3.11+, stdlib `subprocess`/`tempfile`/`difflib`, the existing pipeline + `Embedder` seam, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-15-evaluation-design.md`.

## Global Constraints

- **$0 cost posture (hard):** all harness/scoring/mining/report LOGIC is unit-tested offline with `FakeLLMClient` + `FakeEmbedder` + `embeddings=False`, in CI. The metric-generating runs use real Ollama locally ($0) via `docsmith evaluate` / `make eval` — **never in CI**. Claude is opt-in (`--backend claude`).
- **Evaluation only measures** the existing pipeline — no new detection/repair logic.
- **Error handling:** a case whose pipeline raises a fixture-level error (`ValueError`/`KeyError`/`TypeError`/`OSError`) is scored as a **miss** (empty prediction), never crashing the batch; a backend-unavailable **`RuntimeError` propagates** (fail the run clearly) — same rule as the rest of the project.
- **Doc references use BARE symbol names:** the markdown doc parser's identifier regex (`^[A-Za-z_][A-Za-z0-9_]*$`) does NOT match backtick tokens containing parens, so curated/mined doc sections must reference a symbol as `` `create_user` ``, never `` `create_user(name)` `` — otherwise the section won't link and won't be a candidate.
- **Section id scheme:** `DocSection.id` is `"<file>#<heading-slug>"` (e.g. a `## Users` heading in `README.md` → `README.md#users`). Gold `stale_section_ids` use this scheme.
- **Tests live under `tests/`** (`testpaths=["tests"]`), importing from `evaluation.*` (a namespace package — no `evaluation/__init__.py` needed). ruff line-length 100, select `E,F,I,UP,B`; docstrings Args/Returns/Raises; TDD; frequent commits; **no LLM/AI attribution** in commits. Do NOT edit `docs/planning/roadmap.md` or `CHANGELOG.md` — living docs are controller-managed.

---

## File Structure

- `evaluation/models.py` (create) — `Gold`, `Case`, `CaseResult`, `MetricsReport`.
- `evaluation/materialize.py` (create) — `materialize_case`.
- `evaluation/scoring.py` (create) — detection + correction scoring, `aggregate_report`.
- `evaluation/corpus.py` (create) + `evaluation/data/curated/*.json` (create) — curated case loader + starter corpus.
- `evaluation/runner.py` (create) — `evaluate_cases`, `run_suite`.
- `evaluation/history_replay/mine.py` (create) — `mine_cases`.
- `evaluation/report.py` (replace stub) — `load_run`, `render_table`, `update_readme`.
- `docsmith.py` (modify) — `evaluate` subcommand.
- `Makefile` (modify), `README.md` (modify), `tests/integration/test_evaluate_ollama.py` (create) — targets, Results section, gated real run.

---

## Task 0: Evaluation data models

**Files:**
- Create: `evaluation/models.py`
- Test: `tests/unit/test_eval_models.py`

**Interfaces — Produces:**
- `Gold` (frozen): `stale_section_ids: frozenset[str]`, `fixes: dict[str, str]` (default empty).
- `Case` (frozen): `case_id: str`, `base_files: dict[str, str]`, `head_files: dict[str, str]`, `gold: Gold`.
- `CaseResult` (frozen): `case_id: str`, `tp: int`, `fp: int`, `fn: int`, `corrections: tuple[dict, ...]` (default empty).
- `MetricsReport` (frozen): `suite: str`, `backend: str`, `model: str`, `n_cases: int`, `tp: int`, `fp: int`, `fn: int`, `precision: float`, `recall: float`, `f1: float`, `n_corrections: int`, `exact_match_rate: float`, `mean_similarity: float`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_eval_models.py`:

```python
from evaluation.models import Case, CaseResult, Gold, MetricsReport


def test_case_and_gold():
    gold = Gold(stale_section_ids=frozenset({"README.md#users"}), fixes={"README.md#users": "new"})
    case = Case(case_id="c1", base_files={"a.py": "x"}, head_files={"a.py": "y"}, gold=gold)
    assert case.gold.stale_section_ids == frozenset({"README.md#users"})
    assert case.head_files["a.py"] == "y"


def test_result_defaults():
    r = CaseResult(case_id="c1", tp=1, fp=0, fn=0)
    assert r.corrections == ()


def test_metrics_report_fields():
    m = MetricsReport(
        suite="curated", backend="fake", model="none", n_cases=2, tp=1, fp=0, fn=1,
        precision=1.0, recall=0.5, f1=0.666, n_corrections=1, exact_match_rate=1.0,
        mean_similarity=0.9,
    )
    assert m.f1 == 0.666 and m.precision == 1.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_eval_models.py -v`
Expected: FAIL — `evaluation.models` does not exist.

- [ ] **Step 3: Implement**

Create `evaluation/models.py`:

```python
"""Data models for the evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Gold:
    """Ground-truth labels for one replay case.

    Attributes:
        stale_section_ids: Section ids that SHOULD be flagged stale (empty = a negative case).
        fixes: Section id → expected corrected text (may be empty for detection-only cases).
    """

    stale_section_ids: frozenset[str]
    fixes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Case:
    """A self-contained replay case as file-pairs plus gold labels.

    Attributes:
        case_id: Unique identifier.
        base_files: repo-relative path → content for the base revision.
        head_files: repo-relative path → content for the head revision.
        gold: Ground-truth labels.
    """

    case_id: str
    base_files: dict[str, str]
    head_files: dict[str, str]
    gold: Gold


@dataclass(frozen=True)
class CaseResult:
    """Scored outcome for one case.

    Attributes:
        case_id: The case's id.
        tp: Correctly-flagged sections. fp: Wrongly-flagged. fn: Missed stale sections.
        corrections: Per-correction scores ``{"exact": bool, "similarity": float}``.
    """

    case_id: str
    tp: int
    fp: int
    fn: int
    corrections: tuple[dict, ...] = ()


@dataclass(frozen=True)
class MetricsReport:
    """Aggregated metrics for a suite run.

    Attributes:
        suite/backend/model: Run identity. n_cases: cases scored.
        tp/fp/fn: summed detection counts. precision/recall/f1: derived.
        n_corrections: corrections scored. exact_match_rate/mean_similarity: correction quality.
    """

    suite: str
    backend: str
    model: str
    n_cases: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    n_corrections: int
    exact_match_rate: float
    mean_similarity: float
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_eval_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evaluation/models.py tests/unit/test_eval_models.py
git commit -m "feat: evaluation data models"
```

---

## Task 1: Case materializer

**Files:**
- Create: `evaluation/materialize.py`
- Test: `tests/unit/test_eval_materialize.py`

**Interfaces:**
- Consumes: `Case` (`evaluation/models.py`).
- Produces: `materialize_case(case: Case, workdir: str) -> tuple[str, str, str]` — writes a two-commit git repo under `workdir` (base commit from `base_files`, head commit from `head_files`), returns `(repo_path, base_sha, head_sha)`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_eval_materialize.py`:

```python
import subprocess

from evaluation.materialize import materialize_case
from evaluation.models import Case, Gold


def _show(repo, ref, path):
    return subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{path}"], check=True, capture_output=True, text=True
    ).stdout


def test_materialize_creates_two_commits(tmp_path):
    case = Case(
        case_id="c1",
        base_files={"app.py": "def f():\n    return 1\n", "README.md": "# D\n\nUse `f`.\n"},
        head_files={"app.py": "def f(x):\n    return x\n", "README.md": "# D\n\nUse `f`.\n"},
        gold=Gold(stale_section_ids=frozenset()),
    )
    repo, base, head = materialize_case(case, str(tmp_path))
    assert base != head
    assert _show(repo, base, "app.py") == "def f():\n    return 1\n"
    assert _show(repo, head, "app.py") == "def f(x):\n    return x\n"
    # README identical across both commits (docs unchanged in this case)
    assert _show(repo, base, "README.md") == _show(repo, head, "README.md")


def test_materialize_handles_file_removal(tmp_path):
    case = Case(
        case_id="c2",
        base_files={"a.py": "x\n", "b.py": "y\n"},
        head_files={"a.py": "x2\n"},   # b.py removed at head
        gold=Gold(stale_section_ids=frozenset()),
    )
    repo, base, head = materialize_case(case, str(tmp_path))
    files_at_head = subprocess.run(
        ["git", "-C", repo, "ls-tree", "--name-only", head], check=True, capture_output=True, text=True
    ).stdout.split()
    assert "a.py" in files_at_head and "b.py" not in files_at_head
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_eval_materialize.py -v`
Expected: FAIL — `evaluation.materialize` does not exist.

- [ ] **Step 3: Implement**

Create `evaluation/materialize.py`:

```python
"""Materialize a Case into a scratch two-commit git repo the pipeline can replay."""

from __future__ import annotations

import os
import subprocess

from evaluation.models import Case


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _rev(repo: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _write_tree(repo: str, files: dict[str, str]) -> None:
    """Replace the repo's non-.git contents with ``files``."""
    for entry in os.listdir(repo):
        if entry == ".git":
            continue
        path = os.path.join(repo, entry)
        subprocess.run(["rm", "-rf", path], check=True)
    for rel, content in files.items():
        dest = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(dest) or repo, exist_ok=True)
        with open(dest, "w") as fh:
            fh.write(content)


def materialize_case(case: Case, workdir: str) -> tuple[str, str, str]:
    """Build a two-commit git repo (base → head) for a case.

    Args:
        case: The case to materialize.
        workdir: A directory to create the repo under.

    Returns:
        ``(repo_path, base_sha, head_sha)``.
    """
    repo = os.path.join(workdir, "repo")
    os.makedirs(repo, exist_ok=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "eval@example.com")
    _git(repo, "config", "user.name", "Docsmith Eval")

    _write_tree(repo, case.base_files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _rev(repo)

    _write_tree(repo, case.head_files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "head")
    head = _rev(repo)

    return repo, base, head
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_eval_materialize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evaluation/materialize.py tests/unit/test_eval_materialize.py
git commit -m "feat: materialize eval cases into scratch git repos"
```

---

## Task 2: Scoring

**Files:**
- Create: `evaluation/scoring.py`
- Test: `tests/unit/test_eval_scoring.py`

**Interfaces:**
- Consumes: `CaseResult`, `MetricsReport` (`evaluation/models.py`), the `Embedder` seam (`src/index/embeddings.py`, `embed_texts(list[str]) -> list[list[float]]`).
- Produces: `score_detection(predicted: set[str], gold: set[str]) -> tuple[int, int, int]`; `score_correction(predicted_text: str, gold_text: str, embedder) -> dict`; `aggregate_report(results: list[CaseResult], *, suite: str, backend: str, model: str) -> MetricsReport`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_eval_scoring.py`:

```python
from evaluation.models import CaseResult
from evaluation.scoring import aggregate_report, score_correction, score_detection
from src.index.embeddings import FakeEmbedder


def test_score_detection_counts():
    assert score_detection({"a", "b"}, {"a", "c"}) == (1, 1, 1)      # tp=a, fp=b, fn=c
    assert score_detection(set(), {"a"}) == (0, 0, 1)                 # missed
    assert score_detection({"a"}, set()) == (0, 1, 0)                 # false positive
    assert score_detection(set(), set()) == (0, 0, 0)                 # clean negative


def test_score_correction_exact_and_similarity():
    emb = FakeEmbedder()
    same = score_correction("Use `f`.", "Use  `f`.\n", emb)          # whitespace-normalized equal
    assert same["exact"] is True and same["similarity"] > 0.99
    diff = score_correction("totally different", "Use `f`.", emb)
    assert diff["exact"] is False and diff["similarity"] < 0.99


def test_aggregate_report_metrics():
    results = [
        CaseResult("p1", tp=1, fp=0, fn=0, corrections=({"exact": True, "similarity": 1.0},)),
        CaseResult("p2", tp=0, fp=0, fn=1),                          # missed one
        CaseResult("n1", tp=0, fp=0, fn=0),                          # clean negative
    ]
    m = aggregate_report(results, suite="curated", backend="fake", model="none")
    assert (m.tp, m.fp, m.fn) == (1, 0, 1)
    assert m.precision == 1.0                                        # 1/(1+0)
    assert m.recall == 0.5                                           # 1/(1+1)
    assert round(m.f1, 3) == 0.667
    assert m.n_corrections == 1 and m.exact_match_rate == 1.0 and m.mean_similarity == 1.0
    assert m.n_cases == 3


def test_aggregate_report_zero_guards():
    m = aggregate_report([CaseResult("n", 0, 0, 0)], suite="s", backend="b", model="m")
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0
    assert m.exact_match_rate == 0.0 and m.mean_similarity == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_eval_scoring.py -v`
Expected: FAIL — `evaluation.scoring` does not exist.

- [ ] **Step 3: Implement**

Create `evaluation/scoring.py`:

```python
"""Scoring for the evaluation harness: detection metrics + correction quality."""

from __future__ import annotations

from evaluation.models import CaseResult, MetricsReport


def score_detection(predicted: set[str], gold: set[str]) -> tuple[int, int, int]:
    """Return ``(tp, fp, fn)`` for one case's flagged sections vs. the gold set."""
    tp = len(predicted & gold)
    fp = len(predicted - gold)
    fn = len(gold - predicted)
    return tp, fp, fn


def _normalize(text: str) -> str:
    return " ".join(text.split())


def score_correction(predicted_text: str, gold_text: str, embedder) -> dict:
    """Score a proposed correction vs. gold.

    Args:
        predicted_text: The repair engine's rewritten section text.
        gold_text: The expected corrected text.
        embedder: An ``Embedder`` (real bge-small in live runs, fake in tests).

    Returns:
        ``{"exact": bool, "similarity": float}`` — normalized-string equality and embedding
        cosine similarity (dot product of unit vectors).
    """
    exact = _normalize(predicted_text) == _normalize(gold_text)
    vecs = embedder.embed_texts([predicted_text, gold_text])
    similarity = sum(a * b for a, b in zip(vecs[0], vecs[1], strict=True))
    return {"exact": exact, "similarity": similarity}


def aggregate_report(
    results: list[CaseResult], *, suite: str, backend: str, model: str
) -> MetricsReport:
    """Aggregate per-case results into a MetricsReport (precision/recall/F1 + correction stats)."""
    tp = sum(r.tp for r in results)
    fp = sum(r.fp for r in results)
    fn = sum(r.fn for r in results)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    corrections = [c for r in results for c in r.corrections]
    n_corr = len(corrections)
    exact_rate = sum(1 for c in corrections if c["exact"]) / n_corr if n_corr else 0.0
    mean_sim = sum(c["similarity"] for c in corrections) / n_corr if n_corr else 0.0

    return MetricsReport(
        suite=suite, backend=backend, model=model, n_cases=len(results),
        tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1,
        n_corrections=n_corr, exact_match_rate=exact_rate, mean_similarity=mean_sim,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_eval_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evaluation/scoring.py tests/unit/test_eval_scoring.py
git commit -m "feat: evaluation scoring (detection metrics + correction quality)"
```

---

## Task 3: Curated corpus + loader

**Files:**
- Create: `evaluation/corpus.py`
- Create: `evaluation/data/curated/*.json` (4 starter cases)
- Test: `tests/unit/test_eval_corpus.py`

**Interfaces:**
- Consumes: `Case`, `Gold` (`evaluation/models.py`).
- Produces: `load_curated_cases(root: str = "evaluation/data/curated") -> list[Case]` — reads every `*.json` case file into a `Case`.

**Case JSON schema** (one file per case): `{"case_id": str, "base_files": {path: content}, "head_files": {path: content}, "gold": {"stale_section_ids": [str], "fixes": {section_id: text}}}`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_eval_corpus.py`:

```python
import json

from evaluation.corpus import load_curated_cases


def test_loads_case_files(tmp_path):
    (tmp_path / "sig.json").write_text(json.dumps({
        "case_id": "sig",
        "base_files": {"app.py": "def f():\n    return 1\n"},
        "head_files": {"app.py": "def f(x):\n    return x\n"},
        "gold": {"stale_section_ids": ["README.md#users"], "fixes": {}},
    }))
    cases = load_curated_cases(str(tmp_path))
    assert len(cases) == 1
    assert cases[0].case_id == "sig"
    assert cases[0].gold.stale_section_ids == frozenset({"README.md#users"})


def test_ships_starter_corpus_with_positives_and_negatives():
    cases = load_curated_cases()          # the real bundled corpus
    assert len(cases) >= 4
    positives = [c for c in cases if c.gold.stale_section_ids]
    negatives = [c for c in cases if not c.gold.stale_section_ids]
    assert positives and negatives        # corpus measures both recall and precision
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_eval_corpus.py -v`
Expected: FAIL — `evaluation.corpus` does not exist.

- [ ] **Step 3: Implement the loader**

Create `evaluation/corpus.py`:

```python
"""Load the bundled curated evaluation corpus (one JSON file per case)."""

from __future__ import annotations

import glob
import json
import os

from evaluation.models import Case, Gold


def load_curated_cases(root: str = "evaluation/data/curated") -> list[Case]:
    """Load every ``*.json`` case file under ``root`` into a Case, sorted by id.

    Args:
        root: Directory holding curated case JSON files.

    Returns:
        The loaded cases, ordered by ``case_id``.
    """
    cases: list[Case] = []
    for path in sorted(glob.glob(os.path.join(root, "*.json"))):
        with open(path) as fh:
            raw = json.load(fh)
        gold = raw["gold"]
        cases.append(
            Case(
                case_id=raw["case_id"],
                base_files=raw["base_files"],
                head_files=raw["head_files"],
                gold=Gold(
                    stale_section_ids=frozenset(gold.get("stale_section_ids", [])),
                    fixes=gold.get("fixes", {}),
                ),
            )
        )
    return cases
```

- [ ] **Step 4: Author the 4 starter cases**

Each README references the symbol by BARE name (no parens) so it links. All headings are `## Users` → section id `README.md#users`. Create these files verbatim:

`evaluation/data/curated/py-signature-positive.json`:
```json
{
  "case_id": "py-signature-positive",
  "base_files": {
    "app.py": "def create_user(name):\n    return {\"name\": name}\n",
    "README.md": "# App\n\n## Users\n\nCall `create_user` with a name to make a user.\n"
  },
  "head_files": {
    "app.py": "def create_user(name, email):\n    return {\"name\": name, \"email\": email}\n",
    "README.md": "# App\n\n## Users\n\nCall `create_user` with a name to make a user.\n"
  },
  "gold": {"stale_section_ids": ["README.md#users"], "fixes": {}}
}
```

`evaluation/data/curated/py-removal-positive.json`:
```json
{
  "case_id": "py-removal-positive",
  "base_files": {
    "app.py": "def deactivate(uid):\n    return True\n",
    "README.md": "# App\n\n## Users\n\nUse `deactivate` to disable an account.\n"
  },
  "head_files": {
    "app.py": "def archive(uid):\n    return True\n",
    "README.md": "# App\n\n## Users\n\nUse `deactivate` to disable an account.\n"
  },
  "gold": {"stale_section_ids": ["README.md#users"], "fixes": {}}
}
```

`evaluation/data/curated/py-refactor-negative.json`:
```json
{
  "case_id": "py-refactor-negative",
  "base_files": {
    "app.py": "def total(items):\n    s = 0\n    for i in items:\n        s = s + i\n    return s\n",
    "README.md": "# App\n\n## Totals\n\nCall `total` to sum a list of numbers.\n"
  },
  "head_files": {
    "app.py": "def total(items):\n    return sum(items)\n",
    "README.md": "# App\n\n## Totals\n\nCall `total` to sum a list of numbers.\n"
  },
  "gold": {"stale_section_ids": [], "fixes": {}}
}
```

`evaluation/data/curated/py-comment-negative.json`:
```json
{
  "case_id": "py-comment-negative",
  "base_files": {
    "app.py": "def total(items):\n    return sum(items)\n",
    "README.md": "# App\n\n## Totals\n\nCall `total` to sum a list of numbers.\n"
  },
  "head_files": {
    "app.py": "def total(items):\n    # sum the provided items\n    return sum(items)\n",
    "README.md": "# App\n\n## Totals\n\nCall `total` to sum a list of numbers.\n"
  },
  "gold": {"stale_section_ids": [], "fixes": {}}
}
```

Also create `evaluation/data/curated/README.md` documenting the JSON schema and the bare-name rule, so the corpus is extensible. (Content: a short paragraph describing the four keys and noting doc sections must reference symbols by bare name; headings map to `file#slug` section ids.)

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_eval_corpus.py -v`
Expected: PASS (both the tmp-dir loader test and the bundled-corpus test).

- [ ] **Step 6: Commit**

```bash
git add evaluation/corpus.py evaluation/data/curated/ tests/unit/test_eval_corpus.py
git commit -m "feat: curated evaluation corpus and loader"
```

---

## Task 4: Runner

**Files:**
- Create: `evaluation/runner.py`
- Test: `tests/integration/test_eval_runner.py`

**Interfaces:**
- Consumes: `materialize_case`, `score_detection`/`score_correction`/`aggregate_report`, `Case`/`CaseResult`/`MetricsReport`, `build_index` (`src/index/builder.py`), `investigate_pr`/`repair_pr` (`src/detection/investigator.py`, `src/repair/engine.py`), `Settings` (`src/utils/config.py`), `FakeEmbedder` (`src/index/embeddings.py`), the `LLMClient` seam.
- Produces: `evaluate_cases(cases, client, *, embedder=None, repair=True, embeddings=True) -> list[CaseResult]`; `run_suite(cases, client, *, embedder=None, repair=True, embeddings=True, suite, backend, model) -> tuple[list[CaseResult], MetricsReport]`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_eval_runner.py`:

```python
from evaluation.models import Case, Gold
from evaluation.runner import evaluate_cases, run_suite
from src.index.embeddings import FakeEmbedder
from src.llm.client import FakeLLMClient

POSITIVE = Case(
    case_id="pos",
    base_files={
        "app.py": "def create_user(name):\n    return {\"name\": name}\n",
        "README.md": "# App\n\n## Users\n\nCall `create_user` with a name.\n",
    },
    head_files={
        "app.py": "def create_user(name, email):\n    return {\"name\": name, \"email\": email}\n",
        "README.md": "# App\n\n## Users\n\nCall `create_user` with a name.\n",
    },
    gold=Gold(
        stale_section_ids=frozenset({"README.md#users"}),
        fixes={"README.md#users": "Call `create_user` with a name and email."},
    ),
)


def _stale_client() -> FakeLLMClient:
    def respond(user: str) -> dict:
        if "Rewrite" in user:
            return {"revised_text": "Call `create_user` with a name and email."}
        if "proposed revision" in user:
            return {"accurate": True, "preserved": True, "style_ok": True, "notes": ""}
        return {"stale": True, "confidence": 0.9, "reason": "signature changed",
                "wrong_claims": ["create_user"]}
    return FakeLLMClient(respond)


def test_runner_scores_positive_case(tmp_path):
    results = evaluate_cases(
        [POSITIVE], _stale_client(), embedder=FakeEmbedder(), repair=True, embeddings=False
    )
    assert len(results) == 1
    assert (results[0].tp, results[0].fp, results[0].fn) == (1, 0, 0)
    assert len(results[0].corrections) == 1
    assert results[0].corrections[0]["exact"] is True     # fake rewrite == gold fix


def test_run_suite_aggregates():
    _, report = run_suite(
        [POSITIVE], _stale_client(), embedder=FakeEmbedder(), repair=True, embeddings=False,
        suite="curated", backend="fake", model="none",
    )
    assert report.precision == 1.0 and report.recall == 1.0 and report.f1 == 1.0
    assert report.n_cases == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_eval_runner.py -v`
Expected: FAIL — `evaluation.runner` does not exist.

- [ ] **Step 3: Implement**

Create `evaluation/runner.py`:

```python
"""Replay evaluation cases through the pipeline and score them."""

from __future__ import annotations

import logging
import os
import tempfile

from evaluation.materialize import materialize_case
from evaluation.models import Case, CaseResult, MetricsReport
from evaluation.scoring import aggregate_report, score_correction, score_detection
from src.detection.investigator import investigate_pr
from src.index.builder import build_index
from src.index.embeddings import FakeEmbedder
from src.llm.client import LLMClient
from src.repair.engine import repair_pr
from src.utils.config import Settings

logger = logging.getLogger(__name__)

_FIXTURE_ERRORS = (ValueError, KeyError, TypeError, OSError)


def _predict(case: Case, client: LLMClient, repair: bool, embeddings: bool) -> tuple[set, dict]:
    """Run the pipeline for one case; return (flagged_section_ids, proposed_fixes)."""
    with tempfile.TemporaryDirectory() as workdir:
        repo, base, head = materialize_case(case, workdir)
        index_path = os.path.join(workdir, "index.json")
        build_index(repo, output_path=index_path, embeddings=embeddings, full=True)
        settings = Settings()
        if repair:
            result = repair_pr(repo, base, head, index_path, settings, client)
            flagged = {o.proposal.section_id for o in result.outcomes}
            fixes = {
                o.proposal.section_id: o.proposal.revised_text
                for o in result.outcomes
                if o.proposal.changed
            }
        else:
            inv = investigate_pr(repo, base, head, index_path, settings, client)
            flagged = {v.section_id for v in inv.verdicts if v.stale}
            fixes = {}
    return flagged, fixes


def evaluate_cases(
    cases: list[Case],
    client: LLMClient,
    *,
    embedder=None,
    repair: bool = True,
    embeddings: bool = True,
) -> list[CaseResult]:
    """Score each case by replaying it through the pipeline.

    Args:
        cases: Cases to evaluate.
        client: The LLM client (fake in tests, Ollama/Claude in live runs).
        embedder: Embedder for correction similarity (defaults to a deterministic fake).
        repair: Whether to run the repair stage (needed for correction quality).
        embeddings: Whether to build each case's index with embeddings (False offline).

    Returns:
        One CaseResult per case.

    Raises:
        RuntimeError: If the LLM backend is unavailable (propagated).
    """
    emb = embedder or FakeEmbedder()
    results: list[CaseResult] = []
    for case in cases:
        try:
            flagged, fixes = _predict(case, client, repair, embeddings)
        except RuntimeError:
            raise
        except _FIXTURE_ERRORS as exc:
            logger.warning("Case %s failed to replay: %s", case.case_id, exc)
            flagged, fixes = set(), {}

        gold_sections = set(case.gold.stale_section_ids)
        tp, fp, fn = score_detection(flagged, gold_sections)

        corrections: list[dict] = []
        for section_id in sorted(flagged & gold_sections & set(case.gold.fixes)):
            if section_id in fixes:
                corrections.append(
                    score_correction(fixes[section_id], case.gold.fixes[section_id], emb)
                )
        results.append(CaseResult(case.case_id, tp, fp, fn, tuple(corrections)))
    return results


def run_suite(
    cases: list[Case],
    client: LLMClient,
    *,
    embedder=None,
    repair: bool = True,
    embeddings: bool = True,
    suite: str,
    backend: str,
    model: str,
) -> tuple[list[CaseResult], MetricsReport]:
    """Evaluate a suite of cases and aggregate into a MetricsReport."""
    results = evaluate_cases(
        cases, client, embedder=embedder, repair=repair, embeddings=embeddings
    )
    report = aggregate_report(results, suite=suite, backend=backend, model=model)
    return results, report
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_eval_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + ruff**

Run: `python3 -m pytest -q && python3 -m ruff check evaluation`
Expected: green; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add evaluation/runner.py tests/integration/test_eval_runner.py
git commit -m "feat: evaluation runner replays cases and scores them"
```

---

## Task 5: History-replay mining

**Files:**
- Create: `evaluation/history_replay/mine.py`
- Test: `tests/integration/test_eval_mining.py`

**Interfaces:**
- Consumes: `Case`/`Gold` (`evaluation/models.py`), `parse_source` (`src/parsing/code_parser.py`), `language_for_path` (`src/parsing/languages.py`), the markdown doc parser (`src/parsing/doc_parser.py` — `parse_markdown(content, rel_path) -> list[DocSection]`; verify the exact function name/signature and use it).
- Produces: `mine_cases(repo_path: str, base: str, head: str, *, max_cases: int | None = None) -> list[Case]`.

**Algorithm:** for each commit `C` in `git log base..head` (oldest-first) with parent `P`:
1. `git diff --name-only P C` → split into code files (a supported language via `language_for_path`) and doc files (`*.md`).
2. Skip unless there is ≥1 code file AND ≥1 doc file changed.
3. Changed symbol names: for each changed code file, parse its content at `P` and at `C` (`git show`), diff the sets of `qualified_name`s / bare names; collect the bare names that were added, removed, or whose signature changed. (Reuse the existing symbol-mapping notion loosely: a name counts as "changed" if its source text differs between P and C.)
4. Coupling: for each changed doc file, parse its content **at C** into sections; keep the sections whose `referenced_symbols` intersect the changed bare names. If none couple, skip the commit.
5. Synthesize a `Case`: `base_files` = {each changed doc file @ P} ∪ {each changed code file @ P}; `head_files` = {each changed doc file @ P (UNCHANGED — hide the edit)} ∪ {each changed code file @ C}. `gold.stale_section_ids` = the coupled sections' ids; `gold.fixes` = {coupled section id → its text parsed at C} (the real post-edit text). Stop at `max_cases`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_eval_mining.py` — build a fixture git repo with one coupled commit and one uncoupled, then assert mining keeps only the coupled one:

```python
import subprocess

from evaluation.history_replay.mine import mine_cases


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)


def _setup(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "e@x.com")
    _git(repo, "config", "user.name", "E")
    (repo / "app.py").write_text("def create_user(name):\n    return name\n")
    (repo / "README.md").write_text("# D\n\n## Users\n\nCall `create_user`.\n")
    _commit(repo, "base")
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    # coupled commit: change create_user signature AND its doc section together
    (repo / "app.py").write_text("def create_user(name, email):\n    return name\n")
    (repo / "README.md").write_text("# D\n\n## Users\n\nCall `create_user` with name and email.\n")
    _commit(repo, "coupled")
    # uncoupled commit: unrelated code + a doc typo fix that names no changed symbol
    (repo / "util.py").write_text("def helper():\n    return 2\n")
    (repo / "README.md").write_text("# Docs\n\n## Users\n\nCall `create_user` with name and email.\n")
    _commit(repo, "uncoupled")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    return repo, base, head


def test_mine_keeps_only_coupled_commit(tmp_path):
    repo, base, head = _setup(tmp_path)
    cases = mine_cases(str(repo), base, head)
    assert len(cases) == 1
    case = cases[0]
    assert case.gold.stale_section_ids == frozenset({"README.md#users"})
    # doc hidden at head (equals base doc); code updated at head
    assert case.base_files["README.md"] == case.head_files["README.md"]
    assert "email" in case.head_files["app.py"]
    assert "with name and email" in case.gold.fixes["README.md#users"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_eval_mining.py -v`
Expected: FAIL — `evaluation.history_replay.mine` does not exist.

- [ ] **Step 3: Implement**

First confirm the doc-parser entry point: `grep -n "^def " src/parsing/doc_parser.py` and use the actual function that returns `DocSection`s for markdown content (it exposes `.id` and `.referenced_symbols`). Then create `evaluation/history_replay/mine.py`:

```python
"""Mine a repo's coupled code+doc commits into replay cases (real-world ground truth)."""

from __future__ import annotations

import subprocess

from evaluation.models import Case, Gold
from src.parsing.code_parser import parse_source
from src.parsing.doc_parser import parse_markdown  # verify exact name; adjust import if different
from src.parsing.languages import language_for_path


def _git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    ).stdout


def _show(repo: str, ref: str, path: str) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", repo, "show", f"{ref}:{path}"],
            check=True, capture_output=True, text=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None


def _changed_symbol_names(repo: str, parent: str, commit: str, path: str) -> set[str]:
    """Bare names of symbols whose source text differs between parent and commit."""
    language = language_for_path(path)
    if language is None:
        return set()
    old = _show(repo, parent, path)
    new = _show(repo, commit, path)

    def _by_name(content: str | None) -> dict[str, str]:
        if content is None:
            return {}
        out: dict[str, str] = {}
        for sym in parse_source(content, path, language):
            lines = content.splitlines()
            out[sym.name] = "\n".join(lines[sym.start_line - 1 : sym.end_line])
        return out

    old_syms, new_syms = _by_name(old), _by_name(new)
    changed = set()
    for name in set(old_syms) | set(new_syms):
        if old_syms.get(name) != new_syms.get(name):
            changed.add(name)
    return changed


def mine_cases(
    repo_path: str, base: str, head: str, *, max_cases: int | None = None
) -> list[Case]:
    """Mine coupled code+doc commits in ``base..head`` into replay cases.

    Args:
        repo_path: Path to the git repo to mine.
        base: Older ref (exclusive).
        head: Newer ref (inclusive).
        max_cases: Optional cap on the number of cases returned.

    Returns:
        One Case per commit whose doc edit references a symbol changed in the same commit.
    """
    revs = _git(repo_path, "rev-list", "--reverse", f"{base}..{head}").split()
    cases: list[Case] = []
    for commit in revs:
        parents = _git(repo_path, "rev-list", "--parents", "-n", "1", commit).split()
        if len(parents) < 2:
            continue
        parent = parents[1]
        changed = _git(repo_path, "diff", "--name-only", parent, commit).split()
        code_files = [f for f in changed if language_for_path(f) is not None]
        doc_files = [f for f in changed if f.endswith(".md")]
        if not code_files or not doc_files:
            continue

        changed_names: set[str] = set()
        for f in code_files:
            changed_names |= _changed_symbol_names(repo_path, parent, commit, f)
        if not changed_names:
            continue

        stale_ids: set[str] = set()
        fixes: dict[str, str] = {}
        base_files: dict[str, str] = {}
        head_files: dict[str, str] = {}
        for f in doc_files:
            content_c = _show(repo_path, commit, f)
            content_p = _show(repo_path, parent, f)
            if content_c is None or content_p is None:
                continue
            for section in parse_markdown(content_c, f):
                if set(section.referenced_symbols) & changed_names:
                    stale_ids.add(section.id)
                    fixes[section.id] = section.raw
            base_files[f] = content_p
            head_files[f] = content_p  # doc hidden: head keeps the pre-edit doc
        if not stale_ids:
            continue

        for f in code_files:
            p_content = _show(repo_path, parent, f)
            c_content = _show(repo_path, commit, f)
            if p_content is not None:
                base_files[f] = p_content
            if c_content is not None:
                head_files[f] = c_content

        cases.append(
            Case(
                case_id=f"history-{commit[:10]}",
                base_files=base_files,
                head_files=head_files,
                gold=Gold(stale_section_ids=frozenset(stale_ids), fixes=fixes),
            )
        )
        if max_cases is not None and len(cases) >= max_cases:
            break
    return cases
```

> If `parse_markdown` is not the actual doc-parser function name, adjust the import and call to the real one (it returns `DocSection`s with `.id` and `.referenced_symbols`). Do not invent a signature — read `src/parsing/doc_parser.py` first.

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_eval_mining.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + ruff**

Run: `python3 -m pytest -q && python3 -m ruff check evaluation`
Expected: green; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add evaluation/history_replay/mine.py tests/integration/test_eval_mining.py
git commit -m "feat: history-replay mining of coupled code+doc commits"
```

---

## Task 6: `docsmith evaluate` CLI

**Files:**
- Modify: `docsmith.py`
- Test: `tests/integration/test_cli_evaluate.py`

**Interfaces:**
- Consumes: `run_suite` (`evaluation/runner.py`), `load_curated_cases` (`evaluation/corpus.py`), `mine_cases` (`evaluation/history_replay/mine.py`), `make_client` (`src/detection/investigator.py`), `load_settings`, `MetricsReport`.
- Produces: the `evaluate` subcommand + a `_run_evaluate(args, client, embedder, embeddings) -> MetricsReport` helper (in `docsmith.py`) so the CLI is testable with fakes.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_cli_evaluate.py`:

```python
import json
import sys

import docsmith
from tests.integration.test_eval_runner import POSITIVE, _stale_client


def test_evaluate_curated_writes_run_json(tmp_path, monkeypatch):
    out = tmp_path / "run.json"
    monkeypatch.setattr("evaluation.corpus.load_curated_cases", lambda *a, **k: [POSITIVE])
    monkeypatch.setattr(docsmith, "make_client", lambda settings, backend_override=None: _stale_client())
    monkeypatch.setattr(sys, "argv", [
        "docsmith", "evaluate", "--suite", "curated", "--backend", "fake",
        "--no-embeddings", "--out", str(out),
    ])
    docsmith.main()
    data = json.loads(out.read_text())
    assert data["report"]["precision"] == 1.0
    assert data["report"]["n_cases"] == 1
    assert len(data["results"]) == 1
```

(Note: the branch calls `evaluation.corpus.load_curated_cases(...)` via the module attribute so the monkeypatch of `evaluation.corpus.load_curated_cases` takes effect. `make_client` is patched on `docsmith` since it's imported into that namespace. With `--no-embeddings` the embedder is `None` (so `BgeSmallEmbedder` is never constructed) and the runner falls back to its deterministic `FakeEmbedder` — the test stays fully offline. Add a `--no-embeddings` flag that sets `embeddings=False`.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/integration/test_cli_evaluate.py -v`
Expected: FAIL — no `evaluate` subcommand.

- [ ] **Step 3: Implement the subparser + branch**

In `docsmith.py`, add imports:

```python
import evaluation.corpus
from evaluation.history_replay.mine import mine_cases
from evaluation.runner import run_suite
from src.index.embeddings import BgeSmallEmbedder
```

After the `github-action` subparser, add an `evaluate` subparser with: `--suite` (choices `curated`/`history`, required), `--repo`/`--base`/`--head` (for history), `--backend` (choices fake/ollama/claude, default None), `--model` (default None), `--no-embeddings` (store_true), `--no-repair` (store_true), `--out` (default None). Then add the branch:

```python
    elif args.subcommand == "evaluate":
        settings = load_settings(args.config) if hasattr(args, "config") else load_settings()
        client = make_client(settings, backend_override=args.backend)
        embeddings = not args.no_embeddings
        embedder = BgeSmallEmbedder() if embeddings else None
        report = _run_evaluate(args, client, embedder, embeddings)
        print(
            f"[{report.suite}] cases={report.n_cases} "
            f"P={report.precision:.2f} R={report.recall:.2f} F1={report.f1:.2f} "
            f"| corrections: exact={report.exact_match_rate:.2f} sim={report.mean_similarity:.2f}"
        )
```

Add the helper (top-level in `docsmith.py`), which does the case loading, runs the suite, and writes the run JSON:

```python
def _run_evaluate(args, client, embedder, embeddings):
    """Load the chosen suite, evaluate it, write the run JSON, and return the MetricsReport."""
    import json

    from dataclasses import asdict

    if args.suite == "curated":
        cases = evaluation.corpus.load_curated_cases()
    else:
        cases = mine_cases(args.repo, args.base, args.head)
    backend = args.backend or "ollama"
    model = args.model or ""
    results, report = run_suite(
        cases, client, embedder=embedder, repair=not args.no_repair, embeddings=embeddings,
        suite=args.suite, backend=backend, model=model,
    )
    if args.out:
        payload = {"report": asdict(report), "results": [asdict(r) for r in results]}
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2)
    return report
```

> `--config` may not exist on the `evaluate` subparser; add a `--config` arg (default `configs/base.yaml`) to it so `load_settings(args.config)` works, matching the other subcommands. Backend-unavailable `RuntimeError` propagates and exits non-zero (do not catch it).

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/integration/test_cli_evaluate.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + ruff**

Run: `python3 -m pytest -q && python3 -m ruff check docsmith.py`
Expected: green; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add docsmith.py tests/integration/test_cli_evaluate.py
git commit -m "feat: docsmith evaluate CLI subcommand"
```

---

## Task 7: Reporting

**Files:**
- Modify (replace stub): `evaluation/report.py`
- Test: `tests/unit/test_eval_report.py`

**Interfaces:**
- Consumes: `MetricsReport` (`evaluation/models.py`).
- Produces: `load_run(path: str) -> MetricsReport`; `render_table(report: MetricsReport) -> str`; `update_readme(readme_path: str, table: str, marker: str = "<!-- docsmith:results -->") -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_eval_report.py`:

```python
import json

from evaluation.report import load_run, render_table, update_readme

RUN = {
    "report": {
        "suite": "curated", "backend": "ollama", "model": "qwen2.5-coder:7b", "n_cases": 4,
        "tp": 2, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0,
        "n_corrections": 2, "exact_match_rate": 0.5, "mean_similarity": 0.82,
    },
    "results": [],
}


def test_load_and_render(tmp_path):
    p = tmp_path / "run.json"
    p.write_text(json.dumps(RUN))
    report = load_run(str(p))
    assert report.f1 == 1.0 and report.n_cases == 4
    table = render_table(report)
    assert "Precision" in table and "1.00" in table and "qwen2.5-coder:7b" in table


def test_update_readme_inserts_then_replaces(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Docsmith\n\nintro\n")
    update_readme(str(readme), "TABLE-A")
    first = readme.read_text()
    assert "## Results" in first and "TABLE-A" in first
    update_readme(str(readme), "TABLE-B")
    second = readme.read_text()
    assert "TABLE-B" in second and "TABLE-A" not in second     # replaced, not duplicated
    assert second.count("## Results") == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/unit/test_eval_report.py -v`
Expected: FAIL — `evaluation.report` has no `load_run`.

- [ ] **Step 3: Implement (replace the stub)**

Replace the entire contents of `evaluation/report.py` with:

```python
"""Aggregate an evaluation run into a README metrics table."""

from __future__ import annotations

import json

from evaluation.models import MetricsReport

MARKER = "<!-- docsmith:results -->"


def load_run(path: str) -> MetricsReport:
    """Load the ``report`` section of a run JSON into a MetricsReport."""
    with open(path) as fh:
        data = json.load(fh)
    return MetricsReport(**data["report"])


def render_table(report: MetricsReport) -> str:
    """Render a MetricsReport as a markdown table block (prefixed with the marker)."""
    return "\n".join([
        MARKER,
        "",
        f"_Suite: **{report.suite}** · backend: **{report.backend}** "
        f"({report.model or 'n/a'}) · {report.n_cases} cases_",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Precision | {report.precision:.2f} |",
        f"| Recall | {report.recall:.2f} |",
        f"| F1 | {report.f1:.2f} |",
        f"| Correction exact-match | {report.exact_match_rate:.2f} |",
        f"| Correction similarity | {report.mean_similarity:.2f} |",
    ])


def update_readme(readme_path: str, table: str, marker: str = MARKER) -> None:
    """Insert or replace a marked '## Results' block in the README (idempotent).

    Args:
        readme_path: Path to the README.
        table: The rendered table (its first line is the marker).
        marker: The hidden marker identifying the managed block.
    """
    with open(readme_path) as fh:
        text = fh.read()

    block = f"## Results\n\n{table}\n"
    start = text.find("## Results")
    if start != -1 and marker in text:
        end = text.find("\n## ", start + 1)
        if end == -1:
            end = len(text)
        new_text = text[:start] + block + text[end:]
    else:
        new_text = text.rstrip() + "\n\n" + block

    with open(readme_path, "w") as fh:
        fh.write(new_text)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest tests/unit/test_eval_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evaluation/report.py tests/unit/test_eval_report.py
git commit -m "feat: evaluation report table + README publish"
```

---

## Task 8: Make targets, README Results, gated real run, docs

**Files:**
- Modify: `Makefile`
- Modify: `README.md`
- Create: `tests/integration/test_evaluate_ollama.py`

**Interfaces:** Consumes the `docsmith evaluate` CLI, `run_suite`, `load_curated_cases`.

- [ ] **Step 1: Write the gated real-Ollama test (skips cleanly)**

Mirror `tests/integration/test_repair_ollama.py`'s skip guard. Create `tests/integration/test_evaluate_ollama.py`:

```python
import os
import socket
from urllib.parse import urlparse

import pytest

from evaluation.corpus import load_curated_cases
from evaluation.runner import run_suite
from src.detection.investigator import make_client
from src.index.embeddings import BgeSmallEmbedder
from src.utils.config import load_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_OLLAMA_TESTS") != "1",
    reason="set DOCSMITH_RUN_OLLAMA_TESTS=1 to run the real-Ollama evaluation test",
)


def _reachable(host: str) -> bool:
    p = urlparse(host)
    try:
        with socket.create_connection((p.hostname, p.port or 11434), timeout=1):
            return True
    except OSError:
        return False


def test_curated_eval_on_real_ollama():
    settings = load_settings("configs/base.yaml")
    if not _reachable(settings.ollama_host):
        pytest.skip("Ollama not reachable")
    cases = load_curated_cases()
    client = make_client(settings, backend_override="ollama")
    _, report = run_suite(
        cases, client, embedder=BgeSmallEmbedder(), repair=True, embeddings=True,
        suite="curated", backend="ollama", model=settings.ollama_model,
    )
    assert report.n_cases == len(cases)
    assert 0.0 <= report.precision <= 1.0 and 0.0 <= report.recall <= 1.0
```

- [ ] **Step 2: Run to verify it SKIPS cleanly**

Run: `python3 -m pytest tests/integration/test_evaluate_ollama.py -rs -v`
Expected: `1 skipped`, reason shown, no collection error.

- [ ] **Step 3: Add Make targets**

In `Makefile`, add to `.PHONY` and add targets:

```makefile
.PHONY: eval eval-report
eval:
	python docsmith.py evaluate --suite curated --backend ollama --out evaluation/data/runs/curated.json

eval-report:
	python -c "from evaluation.report import load_run, render_table, update_readme; update_readme('README.md', render_table(load_run('evaluation/data/runs/curated.json')))"
```

- [ ] **Step 4: Add the README Results section + reproduce docs**

In `README.md`, add a `## Results` section containing the marker `<!-- docsmith:results -->` and a placeholder line ("_Run `make eval && make eval-report` to populate (free, local, on Ollama)._"), plus a short "## Evaluation" note describing the curated corpus + history-replay harness, how to reproduce (`make eval`), and that the demo video + Marketplace publish are manual follow-ups. Ensure `evaluation/data/runs/` exists with a `.gitkeep` (the run JSONs are git-ignored).

- [ ] **Step 5: Full suite (gated test skipped) + ruff**

Run: `python3 -m pytest -q -rs && python3 -m ruff check .`
Expected: all pass with the real-Ollama eval test SKIPPED; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add Makefile README.md tests/integration/test_evaluate_ollama.py evaluation/data/runs/.gitkeep
git commit -m "feat: eval make targets, README results section, gated ollama eval test"
```

---

## Definition of Done (from the spec)

- `docsmith evaluate --suite curated --backend ollama` produces reproducible detection precision/recall/F1 + correction quality on the bundled corpus at **$0**.
- The history-replay harness mines a real repo's coupled code+doc commits and replays them, reporting the same metrics.
- `report.py` renders a metrics table and publishes it to the README "## Results" section.
- Default `pytest` suite stays fully offline ($0) and green; `ruff check .` clean; no evaluation code runs a real LLM in CI.
- README documents reproduction (`make eval`) and notes the demo-video / Marketplace steps as manual follow-ups.
- No LLM/AI attribution in any commit; living docs updated by the controller, not task implementers.
