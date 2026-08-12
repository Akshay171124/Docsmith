"""Claude Sonnet client wrapper with structured-output helpers.

Defines the ``LLMClient`` protocol that every concrete client (fake, Ollama,
Claude) implements, plus ``FakeLLMClient``, a scripted offline stand-in used
in tests. Concrete network-backed clients (``OllamaClient``, ``ClaudeClient``)
are added in later tasks in this same module.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Generic seam for requesting a JSON-shaped completion from an LLM."""

    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...


class FakeLLMClient:
    """Scripted, offline stand-in for LLMClient used in tests.

    Constructed with either a fixed response dict, or a callable that maps
    the ``user`` prompt to a response dict.
    """

    def __init__(self, response: dict | Callable[[str], dict]) -> None:
        self._response = response
        self.last_call: tuple[str, str, dict] | None = None

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        self.last_call = (system, user, schema)
        if callable(self._response):
            return self._response(user)
        return self._response
