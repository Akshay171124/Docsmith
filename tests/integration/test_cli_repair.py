"""Integration tests for the `docsmith repair` CLI subcommand."""

from __future__ import annotations

import sys

import docsmith
from src.detection.models import RepairRoute  # noqa: F401  (ensures import path is valid)
from tests.integration.test_repair_pr import _fake_pipeline_client, _setup_repo


def test_cli_repair_prints_autofix_and_diff(tmp_path, monkeypatch, capsys):
    repo, base, head, index_path = _setup_repo(tmp_path)
    monkeypatch.setattr(
        docsmith,
        "make_client",
        lambda settings, backend_override=None: _fake_pipeline_client(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docsmith", "repair",
            "--repo", str(repo),
            "--base", base,
            "--head", head,
            "--index", index_path,
            "--backend", "fake",
        ],
    )
    docsmith.main()
    out = capsys.readouterr().out
    assert "AUTOFIX" in out
    assert "README.md#users" in out
    assert "create_user(name, email)" in out
    assert "auto-fixable" in out  # rollup line


def test_cli_repair_backend_unavailable_exits_1(tmp_path, monkeypatch, capsys):
    repo, base, head, index_path = _setup_repo(tmp_path)

    def boom(repo_root, base, head, index_path, settings, client):
        raise RuntimeError(
            "Could not reach Ollama at http://localhost:11434 — run `ollama pull ...`"
        )

    monkeypatch.setattr(docsmith, "make_client", lambda settings, backend_override=None: object())
    monkeypatch.setattr(docsmith, "repair_pr", boom)
    monkeypatch.setattr(
        sys, "argv",
        ["docsmith", "repair", "--repo", str(repo), "--base", base, "--head", head,
         "--index", index_path, "--backend", "ollama"],
    )
    try:
        docsmith.main()
        raised = False
    except SystemExit as exc:
        raised = True
        assert exc.code == 1
    assert raised
    err = capsys.readouterr().err
    assert "Ollama" in err
