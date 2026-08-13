"""Tests for ClaudeClient, the optional paid Anthropic-SDK backend for LLMClient."""

from __future__ import annotations

import importlib
import sys

import pytest

from src.llm.client import ClaudeClient


@pytest.fixture(autouse=True)
def _keep_anthropic_import_isolated():
    """Remove ``anthropic`` from ``sys.modules`` after each test.

    Several tests in this file deliberately trigger the lazy ``import
    anthropic`` inside ``ClaudeClient``. Without this cleanup, the module
    would stay cached in ``sys.modules`` and break other tests (e.g.
    ``test_llm_client_fake.py``) that assert importing ``src.llm.client``
    never pulls in ``anthropic``.
    """
    yield
    sys.modules.pop("anthropic", None)


def test_importing_client_module_does_not_import_anthropic() -> None:
    sys.modules.pop("anthropic", None)
    sys.modules.pop("src.llm.client", None)

    importlib.import_module("src.llm.client")

    assert "anthropic" not in sys.modules


def test_constructing_client_does_not_import_anthropic() -> None:
    sys.modules.pop("anthropic", None)

    ClaudeClient()

    assert "anthropic" not in sys.modules


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text
        self.last_call: dict | None = None

    def create(self, **kwargs: object) -> _FakeMessage:
        self.last_call = kwargs
        return _FakeMessage(self._response_text)


class _FakeAnthropicClient:
    def __init__(self, response_text: str) -> None:
        self.messages = _FakeMessages(response_text)


def test_complete_json_returns_parsed_verdict_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = {
        "stale": True,
        "confidence": 0.9,
        "reason": "...",
        "wrong_claims": ["..."],
    }
    import json as _json

    fake_client = _FakeAnthropicClient(_json.dumps(verdict))
    monkeypatch.setattr(ClaudeClient, "_anthropic_client", lambda self: fake_client)

    client = ClaudeClient(model="claude-sonnet-5")
    schema = {"type": "object", "properties": {"stale": {"type": "boolean"}}}

    result = client.complete_json("system prompt", "user prompt", schema)

    assert result == verdict


def test_complete_json_sends_model_schema_and_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeAnthropicClient("{}")
    monkeypatch.setattr(ClaudeClient, "_anthropic_client", lambda self: fake_client)

    client = ClaudeClient(model="claude-sonnet-5")
    schema = {"type": "object", "properties": {"stale": {"type": "boolean"}}}

    client.complete_json("system prompt", "user prompt", schema)

    call = fake_client.messages.last_call
    assert call is not None
    assert call["model"] == "claude-sonnet-5"
    assert call["system"] == "system prompt"
    assert call["messages"] == [{"role": "user", "content": "user prompt"}]
    assert call["output_config"]["format"]["schema"] == schema
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_auth_failure_raises_clear_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_auth_error(self: ClaudeClient) -> object:
        import anthropic

        raise anthropic.AuthenticationError(
            message="invalid x-api-key",
            response=_make_fake_response(401),
            body=None,
        )

    monkeypatch.setattr(ClaudeClient, "_anthropic_client", _raise_auth_error)

    client = ClaudeClient(model="claude-sonnet-5")

    with pytest.raises(RuntimeError) as exc_info:
        client.complete_json("s", "u", {})

    message = str(exc_info.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "--backend ollama" in message


def _make_fake_response(status_code: int) -> object:
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code=status_code, request=request)


def test_malformed_json_response_is_not_swallowed_as_auth_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeAnthropicClient("not valid json")
    monkeypatch.setattr(ClaudeClient, "_anthropic_client", lambda self: fake_client)

    client = ClaudeClient(model="claude-sonnet-5")

    with pytest.raises(Exception) as exc_info:
        client.complete_json("s", "u", {})

    assert "ANTHROPIC_API_KEY" not in str(exc_info.value)
