"""Tests for the LLMClient protocol and FakeLLMClient scripted stand-in."""

from __future__ import annotations

import sys

from src.llm.client import FakeLLMClient, LLMClient


def test_fixed_dict_response() -> None:
    response = {"stale": True, "confidence": 0.9, "reason": "r", "wrong_claims": []}
    client = FakeLLMClient(response)

    assert client.complete_json("s", "u", {}) == response


def test_callable_response_maps_user_prompt() -> None:
    client = FakeLLMClient(lambda user: {"stale": "foo" in user})

    assert client.complete_json("s", "this has foo in it", {}) == {"stale": True}
    assert client.complete_json("s", "nothing relevant", {}) == {"stale": False}


def test_isinstance_protocol_conformance() -> None:
    assert isinstance(FakeLLMClient({}), LLMClient)


def test_importing_client_module_does_not_import_anthropic() -> None:
    import src.llm.client  # noqa: F401

    assert "anthropic" not in sys.modules


def test_last_call_records_request() -> None:
    client = FakeLLMClient({"ok": True})
    schema = {"type": "object"}

    client.complete_json("sys-prompt", "user-prompt", schema)

    assert client.last_call == ("sys-prompt", "user-prompt", schema)
