"""Integration tests for the build-index CLI subcommand."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).parents[2]
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "sample_repo"


def test_build_index_cli_exit_zero(tmp_path: pathlib.Path) -> None:
    """build-index subcommand exits with code 0."""
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
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"CLI exited with {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_build_index_cli_output_file_exists(tmp_path: pathlib.Path) -> None:
    """build-index writes the index JSON file to --output."""
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
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    assert output.exists(), f"Expected {output} to exist after build-index"


def test_build_index_cli_json_structure(tmp_path: pathlib.Path) -> None:
    """The written JSON has symbols, sections, and links keys."""
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
