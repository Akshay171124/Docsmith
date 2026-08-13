"""Tests for staleness prompt templates and the verdict JSON schema."""

from __future__ import annotations

from src.detection.models import ChangeKind, InvestigationInput
from src.llm.prompts import SYSTEM_PROMPT, VERDICT_SCHEMA, build_staleness_prompt


def _signature_changed_input() -> InvestigationInput:
    return InvestigationInput(
        symbol_id="app.py::create_user",
        section_id="sec-001",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        symbol_name="create_user",
        old_code="def create_user(name):",
        new_code="def create_user(name, email):",
        doc_section_text="Call create_user(name) to make a user.",
    )


def test_build_staleness_prompt_contains_all_key_pieces() -> None:
    prompt = build_staleness_prompt(_signature_changed_input())

    assert "create_user" in prompt
    assert "def create_user(name):" in prompt
    assert "def create_user(name, email):" in prompt
    assert "Call create_user(name) to make a user." in prompt
    assert "signature_changed" in prompt.lower() or "SIGNATURE_CHANGED" in prompt


def test_build_staleness_prompt_handles_added_symbol_with_no_old_code() -> None:
    inp = InvestigationInput(
        symbol_id="app.py::new_func",
        section_id="sec-002",
        change_kind=ChangeKind.ADDED,
        symbol_name="new_func",
        old_code=None,
        new_code="def new_func(): ...",
        doc_section_text="Some doc text.",
    )

    prompt = build_staleness_prompt(inp)

    assert "no previous version" in prompt.lower()
    assert "new_func" in prompt


def test_build_staleness_prompt_handles_removed_symbol_with_no_new_code() -> None:
    inp = InvestigationInput(
        symbol_id="app.py::old_func",
        section_id="sec-003",
        change_kind=ChangeKind.REMOVED,
        symbol_name="old_func",
        old_code="def old_func(): ...",
        new_code=None,
        doc_section_text="Some doc text.",
    )

    prompt = build_staleness_prompt(inp)

    assert "no new version" in prompt.lower()
    assert "old_func" in prompt


def test_verdict_schema_shape() -> None:
    assert VERDICT_SCHEMA["type"] == "object"
    assert set(VERDICT_SCHEMA["properties"]) == {"stale", "confidence", "reason", "wrong_claims"}
    assert VERDICT_SCHEMA["additionalProperties"] is False
    for key in ("stale", "confidence", "reason", "wrong_claims"):
        assert key in VERDICT_SCHEMA["required"]


def test_system_prompt_is_nonempty_and_mentions_staleness() -> None:
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 0
    assert "stale" in SYSTEM_PROMPT.lower()
