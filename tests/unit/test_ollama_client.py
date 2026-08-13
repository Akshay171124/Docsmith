"""Tests for OllamaClient, the local/free LLM backend for LLMClient."""

from __future__ import annotations

import json
import urllib.error

import pytest

from src.llm.client import OllamaClient


def test_complete_json_returns_parsed_verdict_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    verdict = {
        "stale": True,
        "confidence": 0.9,
        "reason": "...",
        "wrong_claims": ["..."],
    }
    captured_payload: dict = {}

    def fake_post(self: OllamaClient, url: str, payload: dict) -> dict:
        captured_payload.update(payload)
        return {"message": {"role": "assistant", "content": json.dumps(verdict)}}

    monkeypatch.setattr(OllamaClient, "_post", fake_post)

    client = OllamaClient(model="llama3", host="http://localhost:11434")
    schema = {"type": "object", "properties": {"stale": {"type": "boolean"}}}

    result = client.complete_json("system prompt", "user prompt", schema)

    assert result == verdict


def test_complete_json_sends_schema_and_both_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_payload: dict = {}

    def fake_post(self: OllamaClient, url: str, payload: dict) -> dict:
        captured_payload.update(payload)
        return {"message": {"role": "assistant", "content": "{}"}}

    monkeypatch.setattr(OllamaClient, "_post", fake_post)

    client = OllamaClient(model="llama3", host="http://localhost:11434")
    schema = {"type": "object", "properties": {"stale": {"type": "boolean"}}}

    client.complete_json("system prompt", "user prompt", schema)

    assert captured_payload["format"] == schema
    assert captured_payload["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert captured_payload["model"] == "llama3"
    assert captured_payload["stream"] is False
    assert captured_payload["options"] == {"temperature": 0}


def test_complete_json_posts_to_host_api_chat_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_url: dict = {}

    def fake_post(self: OllamaClient, url: str, payload: dict) -> dict:
        captured_url["url"] = url
        return {"message": {"role": "assistant", "content": "{}"}}

    monkeypatch.setattr(OllamaClient, "_post", fake_post)

    client = OllamaClient(model="llama3", host="http://localhost:11434")
    client.complete_json("s", "u", {})

    assert captured_url["url"] == "http://localhost:11434/api/chat"


def test_connection_error_raises_clear_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(self: OllamaClient, url: str, payload: dict) -> dict:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(OllamaClient, "_post", fake_post)

    client = OllamaClient(model="llama3", host="http://localhost:11434")

    with pytest.raises(RuntimeError) as exc_info:
        client.complete_json("s", "u", {})

    message = str(exc_info.value)
    assert "Ollama" in message
    assert "llama3" in message
