"""Tests for the LLM staleness investigator core (`investigate`)."""

from __future__ import annotations

from src.detection.investigator import investigate
from src.detection.models import ChangeKind, InvestigationInput
from src.llm.client import FakeLLMClient


def _input(
    symbol_id: str = "m.py::foo",
    section_id: str = "README.md#u",
    symbol_name: str = "foo",
) -> InvestigationInput:
    return InvestigationInput(
        symbol_id=symbol_id,
        section_id=section_id,
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        symbol_name=symbol_name,
        old_code=f"def {symbol_name}(x):\n    return x\n",
        new_code=f"def {symbol_name}(x, y):\n    return x + y\n",
        doc_section_text=f"Call {symbol_name}(x).",
    )


def test_valid_verdict_produces_one_verdict() -> None:
    inp = _input()
    fake = FakeLLMClient(
        {"stale": True, "confidence": 0.9, "reason": "sig changed", "wrong_claims": ["takes 1 arg"]}
    )

    result = investigate([inp], fake)

    assert len(result.verdicts) == 1
    verdict = result.verdicts[0]
    assert verdict.section_id == inp.section_id
    assert verdict.symbol_id == inp.symbol_id
    assert verdict.stale is True
    assert verdict.confidence == 0.9
    assert verdict.wrong_claims == ("takes 1 arg",)
    assert result.skipped == {}


def test_malformed_verdict_missing_stale_is_skipped() -> None:
    inp = _input()
    fake = FakeLLMClient({"confidence": 0.5, "reason": "x", "wrong_claims": []})

    result = investigate([inp], fake)

    assert result.verdicts == []
    assert result.skipped == {"llm_error": 1}


def test_mixed_batch_one_valid_one_malformed() -> None:
    inp_a = _input(symbol_id="m.py::foo", section_id="README.md#a", symbol_name="foo")
    inp_b = _input(symbol_id="m.py::bar", section_id="README.md#b", symbol_name="bar")

    def fake_response(user: str) -> dict:
        if "foo" in user:
            return {"stale": True, "confidence": 0.8, "reason": "ok", "wrong_claims": []}
        return {"confidence": 0.5, "reason": "missing stale key", "wrong_claims": []}

    fake = FakeLLMClient(fake_response)

    result = investigate([inp_a, inp_b], fake)

    assert len(result.verdicts) == 1
    assert result.verdicts[0].section_id == "README.md#a"
    assert result.skipped == {"llm_error": 1}
