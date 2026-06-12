"""Docsmith entry point.

Single CLI entry usable both locally and inside the GitHub Action:

    python docsmith.py build-index --repo . --output .docsmith/index.json
"""

from __future__ import annotations

import argparse

from src.index.builder import build_index


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        prog="docsmith",
        description="Docsmith — keep your docs in sync with your code.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    build_parser = subparsers.add_parser(
        "build-index",
        help="Walk a repository and build the code-docs index.",
    )
    build_parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    build_parser.add_argument(
        "--output",
        default=".docsmith/index.json",
        help="Path to write the index JSON (default: .docsmith/index.json).",
    )
    build_parser.add_argument(
        "--embeddings",
        action="store_true",
        default=False,
        help="Enable hybrid embedding-based linking (requires sentence-transformers).",
    )

    args = parser.parse_args()

    if args.subcommand == "build-index":
        index = build_index(args.repo, output_path=args.output, embeddings=args.embeddings)
        n_symbols = len(index.symbols)
        n_sections = len(index.sections)
        n_links = len(index.links)
        print(
            f"Indexed {n_symbols} symbols, {n_sections} sections,"
            f" {n_links} links -> {args.output}"
        )


if __name__ == "__main__":
    main()
