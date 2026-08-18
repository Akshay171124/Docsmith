from fastapi.testclient import TestClient

import webapp.app as appmod
from webapp.app import app
from webapp.service import AnalyzeResult

client = TestClient(app)

PR_URL = "https://github.com/o/r/pull/1"


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_analyze_ok(monkeypatch):
    summary = {"verified": 1, "auto_fixable": 1, "flagged": 0, "skipped": 0}
    monkeypatch.setattr(
        appmod.service,
        "analyze",
        lambda *a, **k: AnalyzeResult(summary=summary, results=[]),
    )
    resp = client.post("/api/analyze", json={"pr_url": PR_URL, "backend": "fake"})
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
    resp = client.post("/api/analyze", json={"pr_url": PR_URL, "backend": "ollama"})
    assert resp.status_code == 502
    assert "Ollama" in resp.json()["detail"]
