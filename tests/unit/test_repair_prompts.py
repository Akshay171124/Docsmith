from src.detection.models import ChangeKind, RepairInput, RepairProposal
from src.llm.prompts import (
    REPAIR_SCHEMA,
    VALIDATION_SCHEMA,
    build_repair_prompt,
    build_validate_prompt,
)

INP = RepairInput(
    symbol_id="app.py::create_user",
    section_id="README.md#users",
    file="README.md",
    change_kind=ChangeKind.SIGNATURE_CHANGED,
    symbol_name="create_user",
    new_code="def create_user(name, email):\n    ...",
    section_text="Use `create_user(name)` to make a user.",
    reason="create_user now takes an email argument",
    wrong_claims=("create_user(name)",),
    verdict_confidence=0.9,
)


def test_repair_prompt_contains_evidence_and_anchor():
    p = build_repair_prompt(INP)
    assert "Rewrite" in p                       # anchor for the integration fake
    assert "create_user(name, email)" in p      # new code
    assert "Use `create_user(name)` to make a user." in p  # section text
    assert "create_user now takes an email argument" in p  # reason
    assert "create_user(name)" in p             # wrong claim


def test_validate_prompt_contains_both_texts_and_anchor():
    proposal = RepairProposal(
        symbol_id=INP.symbol_id,
        section_id=INP.section_id,
        file=INP.file,
        original_text=INP.section_text,
        revised_text="Use `create_user(name, email)` to make a user.",
        diff="",
        changed=True,
    )
    p = build_validate_prompt(INP, proposal)
    assert "proposed revision" in p             # anchor for the integration fake
    assert "Use `create_user(name)` to make a user." in p        # original
    assert "Use `create_user(name, email)` to make a user." in p  # revised
    assert "def create_user(name, email):" in p                   # new code


def test_schema_shapes():
    assert REPAIR_SCHEMA["required"] == ["revised_text"]
    assert REPAIR_SCHEMA["additionalProperties"] is False
    assert set(VALIDATION_SCHEMA["required"]) == {"accurate", "preserved", "style_ok", "notes"}
    assert VALIDATION_SCHEMA["additionalProperties"] is False
