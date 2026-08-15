from src.detection.models import (
    RepairOutcome,
    RepairProposal,
    RepairResult,
    RepairRoute,
    ValidationResult,
)
from src.github.client import FakeGitHubClient
from src.github.context import PRContext
from src.github.reporter import report
from src.github.summary import MARKER
from src.models import DocSection, Index
from src.utils.config import Settings

CLEAN = ValidationResult(accurate=True, preserved=True, style_ok=True, notes="")
CTX = PRContext(
    repo="o/r", base_sha="b", head_sha="h", pr_number=7, head_ref="feature", base_ref="main"
)


def _index():
    section = DocSection(
        id="README.md#users", heading_path=("Users",), file="README.md", raw="x",
        start_line=1, end_line=1, referenced_symbols=(), referenced_config_keys=(),
    )
    return Index(sections={"README.md#users": section})


def _autofix():
    proposal = RepairProposal(
        symbol_id="app.py::create_user", section_id="README.md#users", file="README.md",
        original_text="old", revised_text="NEW", diff="-old\n+NEW", changed=True,
    )
    return RepairOutcome(
        proposal=proposal, validation=CLEAN, route=RepairRoute.AUTOFIX, reason="signature_changed"
    )


def test_report_opens_fix_pr_and_upserts_comment():
    result = RepairResult(outcomes=[_autofix()], verified=2)
    gh = FakeGitHubClient(fix_pr_url="https://github.com/o/r/pull/12")
    counts = report(result, CTX, Settings(), gh, _index(), lambda p: "old\n")
    assert counts.fixed == 1 and counts.verified == 2 and counts.flagged == 0
    assert counts.fix_pr_url == "https://github.com/o/r/pull/12"
    assert gh.fix_prs[0]["branch"] == "docsmith/fix-pr-7"
    assert gh.fix_prs[0]["files"] == {"README.md": "NEW\n"}
    assert MARKER in gh.comments[7] and "https://github.com/o/r/pull/12" in gh.comments[7]


def test_report_auto_fix_disabled_opens_no_pr():
    result = RepairResult(outcomes=[_autofix()], verified=0)
    gh = FakeGitHubClient()
    settings = Settings(auto_fix=False)
    counts = report(result, CTX, settings, gh, _index(), lambda p: "old\n")
    assert counts.fixed == 1              # counted as an autofix candidate
    assert counts.fix_pr_url is None
    assert gh.fix_prs == []                # but no PR opened
    assert MARKER in gh.comments[7]


def test_report_is_idempotent_reuses_branch_and_comment():
    result = RepairResult(outcomes=[_autofix()], verified=0)
    gh = FakeGitHubClient()
    report(result, CTX, Settings(), gh, _index(), lambda p: "old\n")
    report(result, CTX, Settings(), gh, _index(), lambda p: "old\n")
    assert gh.comment_calls == 2                       # called twice
    assert len(gh.comments) == 1                       # one comment (last wins)
    assert {c["branch"] for c in gh.fix_prs} == {"docsmith/fix-pr-7"}  # same branch reused
