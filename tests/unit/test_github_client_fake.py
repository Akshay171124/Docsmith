from src.github.client import FakeGitHubClient, GitHubClient


def test_fake_is_a_github_client():
    assert isinstance(FakeGitHubClient(), GitHubClient)


def test_fake_records_comment_upsert_last_wins():
    c = FakeGitHubClient()
    c.upsert_summary_comment(7, "first")
    c.upsert_summary_comment(7, "second")
    assert c.comments[7] == "second"     # upsert overwrites
    assert c.comment_calls == 2          # but was called twice


def test_fake_records_fix_pr_and_returns_url():
    c = FakeGitHubClient(fix_pr_url="https://github.com/o/r/pull/5")
    url = c.open_or_update_fix_pr(
        "head", "main", "docsmith/fix-pr-7", {"README.md": "new"}, "t", "b"
    )
    assert url == "https://github.com/o/r/pull/5"
    assert c.fix_prs[0]["branch"] == "docsmith/fix-pr-7"
    assert c.fix_prs[0]["files"] == {"README.md": "new"}
