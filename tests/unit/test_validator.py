import pytest

from src.detection.models import ChangeKind, RepairInput, RepairProposal
from src.llm.client import FakeLLMClient
from src.repair.validator import validate_repair

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
PROPOSAL = RepairProposal(
    symbol_id=INP.symbol_id,
    section_id=INP.section_id,
    file=INP.file,
    original_text=INP.section_text,
    revised_text="Use `create_user(name, email)` to make a user.",
    diff="(diff)",
    changed=True,
)


def test_validate_parses_all_flags():
    client = FakeLLMClient(
        {"accurate": True, "preserved": True, "style_ok": False, "notes": "tone drifted"}
    )
    result = validate_repair(INP, PROPOSAL, client)
    assert result.accurate is True
    assert result.preserved is True
    assert result.style_ok is False
    assert result.notes == "tone drifted"


def test_validate_rejects_non_boolean_flag():
    client = FakeLLMClient({"accurate": "yes", "preserved": True, "style_ok": True, "notes": ""})
    with pytest.raises(ValueError):
        validate_repair(INP, PROPOSAL, client)


def test_validate_rejects_missing_key():
    client = FakeLLMClient({"accurate": True, "preserved": True, "style_ok": True})
    with pytest.raises((ValueError, KeyError)):
        validate_repair(INP, PROPOSAL, client)
