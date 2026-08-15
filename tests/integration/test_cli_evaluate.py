import json
import sys

import docsmith
from tests.integration.test_eval_runner import POSITIVE, _stale_client


def test_evaluate_curated_writes_run_json(tmp_path, monkeypatch):
    out = tmp_path / "run.json"
    monkeypatch.setattr("evaluation.corpus.load_curated_cases", lambda *a, **k: [POSITIVE])
    monkeypatch.setattr(
        docsmith, "make_client", lambda settings, backend_override=None: _stale_client()
    )
    monkeypatch.setattr(sys, "argv", [
        "docsmith", "evaluate", "--suite", "curated", "--backend", "fake",
        "--no-embeddings", "--out", str(out),
    ])
    docsmith.main()
    data = json.loads(out.read_text())
    assert data["report"]["precision"] == 1.0
    assert data["report"]["n_cases"] == 1
    assert len(data["results"]) == 1
