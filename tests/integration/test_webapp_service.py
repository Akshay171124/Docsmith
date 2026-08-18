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
            return {"revised_text": "Call `create_user(name, email)` with a name and email."}
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
