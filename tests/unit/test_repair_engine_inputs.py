from src.detection.models import ChangeKind, FileChange, Suspect, Verdict
from src.models import DocSection, Index
from src.repair.engine import build_repair_inputs

NEW_CODE = "def create_user(name, email):\n    return {}\n"


def _index():
    section = DocSection(
        id="README.md#users",
        heading_path=("Users",),
        file="README.md",
        raw="Use `create_user(name)` to make a user.",
        start_line=1,
        end_line=2,
        referenced_symbols=("create_user",),
        referenced_config_keys=(),
    )
    return Index(sections={"README.md#users": section})


def test_builds_input_joining_change_kind_and_new_code():
    verdict = Verdict(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        stale=True,
        confidence=0.9,
        reason="now takes email",
        wrong_claims=("create_user(name)",),
    )
    suspect = Suspect(
        symbol_id="app.py::create_user",
        section_id="README.md#users",
        change_kind=ChangeKind.SIGNATURE_CHANGED,
        via="index-link",
    )
    fc = FileChange(
        path="app.py", old_content=None, new_content=NEW_CODE, changed_lines=frozenset()
    )
    inputs = build_repair_inputs([verdict], [suspect], [fc], _index())
    assert len(inputs) == 1
    inp = inputs[0]
    assert inp.change_kind is ChangeKind.SIGNATURE_CHANGED   # recovered via the join
    assert inp.symbol_name == "create_user"
    assert inp.section_text == "Use `create_user(name)` to make a user."
    assert inp.new_code is not None and "def create_user(name, email)" in inp.new_code
    assert inp.verdict_confidence == 0.9
    assert inp.wrong_claims == ("create_user(name)",)


def test_skips_verdict_without_matching_suspect_or_section():
    verdict = Verdict(
        symbol_id="app.py::ghost",
        section_id="README.md#missing",
        stale=True,
        confidence=0.9,
        reason="x",
        wrong_claims=(),
    )
    inputs = build_repair_inputs([verdict], [], [], _index())
    assert inputs == []
