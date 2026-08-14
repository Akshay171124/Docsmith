import pytest

from src.detection.models import ChangeKind, RepairInput
from src.llm.client import FakeLLMClient
from src.repair.repairer import repair_section

INP = RepairInput(
    symbol_id="app.py::create_user",
    section_id="README.md#users",
    file="README.md",
    change_kind=ChangeKind.SIGNATURE_CHANGED,
    symbol_name="create_user",
    new_code="def create_user(name, email):\n    ...",
    section_text="Use `create_user(name)` to make a user.",
    reason="now takes email",
    wrong_claims=("create_user(name)",),
    verdict_confidence=0.9,
)


def test_repair_produces_diff_when_changed():
    client = FakeLLMClient({"revised_text": "Use `create_user(name, email)` to make a user."})
    proposal = repair_section(INP, client)
    assert proposal.changed is True
    assert proposal.section_id == "README.md#users"
    assert proposal.original_text == INP.section_text
    assert proposal.revised_text == "Use `create_user(name, email)` to make a user."
    assert "-Use `create_user(name)` to make a user." in proposal.diff
    assert "+Use `create_user(name, email)` to make a user." in proposal.diff


def test_repair_no_op_when_identical():
    client = FakeLLMClient({"revised_text": INP.section_text})
    proposal = repair_section(INP, client)
    assert proposal.changed is False
    assert proposal.diff == ""


def test_repair_rejects_non_string_revised_text():
    client = FakeLLMClient({"revised_text": 123})
    with pytest.raises(ValueError):
        repair_section(INP, client)


def test_repair_rejects_missing_key():
    client = FakeLLMClient({"nope": "x"})
    with pytest.raises((ValueError, KeyError)):
        repair_section(INP, client)
