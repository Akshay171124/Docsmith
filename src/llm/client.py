"""Claude Sonnet client wrapper with structured-output helpers.

Defines the ``LLMClient`` protocol that every concrete client (fake, Ollama,
Claude) implements, plus ``FakeLLMClient``, a scripted offline stand-in used
in tests. Concrete network-backed clients (``OllamaClient``, ``ClaudeClient``)
are added in later tasks in this same module.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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


class OllamaClient:
    """Free, local LLM backend for LLMClient, backed by a running Ollama server.

    Sends chat requests to Ollama's ``/api/chat`` endpoint using stdlib
    ``urllib`` only (no third-party SDK, no API key, no network access at
    import time).
    """

    def __init__(self, model: str, host: str) -> None:
        self.model = model
        self.host = host

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """Request a JSON-shaped completion from the local Ollama server.

        Args:
            system: System prompt describing the task.
            user: User prompt containing the content to analyze.
            schema: JSON schema the model's response must conform to.

        Returns:
            The parsed verdict dict decoded from the model's response.

        Raises:
            RuntimeError: If Ollama is not reachable (connection failure).
        """
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }

        try:
            body = self._post(url, payload)
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host}. Start Ollama and make sure "
                f"the model is available (e.g. `ollama pull {self.model}`)."
            ) from exc

        return json.loads(body["message"]["content"])

    def _post(self, url: str, payload: dict) -> dict:
        """Send a JSON POST request and return the decoded JSON response body.

        Args:
            url: Full URL to POST to.
            payload: JSON-serializable request body.

        Returns:
            The decoded JSON response body.
        """
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
