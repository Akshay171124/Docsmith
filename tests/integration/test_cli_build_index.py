"""Integration tests for the build-index CLI subcommand."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).parents[2]
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def _run_build_index(*extra_args: str, tmp_path: pathlib.Path) -> subprocess.CompletedProcess:
    """Helper: invoke `docsmith.py build-index` with a temp output path."""
    output = tmp_path / "index.json"
    result = subprocess.run(
        [
            sys.executable,
            "docsmith.py",
            "build-index",
            "--repo",
            str(FIXTURE_REPO),
            "--output",
            str(output),
            "--no-embeddings",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return result


def test_build_index_cli_exit_zero(tmp_path: pathlib.Path) -> None:
    """build-index --no-embeddings subcommand exits with code 0."""
    result = _run_build_index(tmp_path=tmp_path)
    assert result.returncode == 0, (
        f"CLI exited with {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_build_index_cli_output_file_exists(tmp_path: pathlib.Path) -> None:
    """build-index --no-embeddings writes the index JSON file to --output."""
    output = tmp_path / "index.json"
    subprocess.run(
        [
            sys.executable,
            "docsmith.py",
            "build-index",
            "--repo",
            str(FIXTURE_REPO),
            "--output",
            str(output),
            "--no-embeddings",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    assert output.exists(), f"Expected {output} to exist after build-index"


def test_build_index_cli_json_structure(tmp_path: pathlib.Path) -> None:
    """The written JSON has symbols, sections, links, and file_hashes keys."""
    output = tmp_path / "index.json"
    subprocess.run(
        [
            sys.executable,
            "docsmith.py",
            "build-index",
            "--repo",
            str(FIXTURE_REPO),
            "--output",
            str(output),
            "--no-embeddings",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    data = json.loads(output.read_text())
    assert "symbols" in data, "JSON missing 'symbols' key"
    assert "sections" in data, "JSON missing 'sections' key"
    assert "links" in data, "JSON missing 'links' key"
    assert "file_hashes" in data, "JSON missing 'file_hashes' key"


def test_build_index_cli_contains_create_user(tmp_path: pathlib.Path) -> None:
    """The index contains a symbol entry with name == 'create_user'."""
    output = tmp_path / "index.json"
    subprocess.run(
        [
            sys.executable,
            "docsmith.py",
            "build-index",
            "--repo",
            str(FIXTURE_REPO),
            "--output",
            str(output),
            "--no-embeddings",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    data = json.loads(output.read_text())
    symbol_names = {sym["name"] for sym in data["symbols"].values()}
    assert "create_user" in symbol_names, (
        f"Expected 'create_user' in symbols, got: {sorted(symbol_names)}"
    )


def test_build_index_no_embeddings_all_links_symbol_match(tmp_path: pathlib.Path) -> None:
    """With --no-embeddings, all links must have via == 'symbol-match'."""
    result = _run_build_index(tmp_path=tmp_path)
    assert result.returncode == 0, (
        f"CLI exited with {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    output = tmp_path / "index.json"
    data = json.loads(output.read_text())
    for link in data["links"]:
        assert link["via"] == "symbol-match", (
            f"Expected all links via='symbol-match', got: {link['via']}"
        )


def test_build_index_incremental_by_default(tmp_path: pathlib.Path) -> None:
    """Second run with an existing index takes the update path (stdout contains 'update:')."""
    output = tmp_path / "index.json"
    base_args = [
        sys.executable,
        "docsmith.py",
        "build-index",
        "--repo",
        str(FIXTURE_REPO),
        "--output",
        str(output),
        "--no-embeddings",
    ]

    # First run: build from scratch
    first = subprocess.run(
        base_args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert first.returncode == 0, (
        f"First run failed.\nstdout: {first.stdout}\nstderr: {first.stderr}"
    )
    assert output.exists(), "Index file should exist after first run"

    # Second run: index exists → should update, not rebuild
    second = subprocess.run(
        base_args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert second.returncode == 0, (
        f"Second run failed.\nstdout: {second.stdout}\nstderr: {second.stderr}"
    )
    data = json.loads(output.read_text())
    assert "symbols" in data and "sections" in data and "links" in data, (
        "Index must still be valid after incremental update"
    )
    assert "update:" in second.stdout, (
        f"Expected 'update:' in stdout on second run (incremental path).\n"
        f"stdout: {second.stdout!r}"
    )


def test_build_index_full_flag_forces_rebuild(tmp_path: pathlib.Path) -> None:
    """--full after an existing index forces a full rebuild (stdout does NOT contain 'update:')."""
    output = tmp_path / "index.json"
    base_args = [
        sys.executable,
        "docsmith.py",
        "build-index",
        "--repo",
        str(FIXTURE_REPO),
        "--output",
        str(output),
        "--no-embeddings",
    ]

    # First run: build initial index
    first = subprocess.run(
        base_args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert first.returncode == 0, (
        f"First run failed.\nstdout: {first.stdout}\nstderr: {first.stderr}"
    )

    # Second run with --full: should rebuild even though index exists
    full_args = [*base_args, "--full"]
    second = subprocess.run(
        full_args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert second.returncode == 0, (
        f"--full run failed.\nstdout: {second.stdout}\nstderr: {second.stderr}"
    )
    data = json.loads(output.read_text())
    assert "symbols" in data and "sections" in data and "links" in data, (
        "Index must be valid after --full rebuild"
    )
    assert "update:" not in second.stdout, (
        f"Expected 'update:' NOT in stdout for --full run (rebuild path).\n"
        f"stdout: {second.stdout!r}"
    )
