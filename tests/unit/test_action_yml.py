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
