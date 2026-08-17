import pytest

from webapp.prfetch import parse_pr_url


def test_parses_valid_pr_url():
    assert parse_pr_url("https://github.com/octo/repo/pull/42") == ("octo", "repo", 42)


def test_parses_with_trailing_slash():
    assert parse_pr_url("https://github.com/octo/repo/pull/42/") == ("octo", "repo", 42)


@pytest.mark.parametrize("bad", [
    "http://github.com/octo/repo/pull/42",       # not https
    "https://gitlab.com/octo/repo/pull/42",      # not github
    "https://github.com/octo/repo/issues/42",    # not a PR
    "https://github.com/octo/repo/pull/abc",     # non-numeric
    "https://github.com/octo/repo",              # no PR
    "not a url",
])
def test_rejects_bad_urls(bad):
    with pytest.raises(ValueError):
        parse_pr_url(bad)
