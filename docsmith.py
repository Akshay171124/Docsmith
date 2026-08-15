"""Docsmith entry point.

Single CLI entry usable both locally and inside the GitHub Action:

    python docsmith.py build-index --repo . --output .docsmith/index.json
"""

from __future__ import annotations

import argparse
import os
import sys

from src.detection.detector import detect
from src.detection.investigator import investigate_pr, make_client
from src.detection.models import RepairRoute
from src.github.action import run_action
from src.index.builder import build_index, update_index
from src.index.store import load_index
from src.repair.engine import repair_pr
from src.utils.config import load_settings


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
        "--full",
        action="store_true",
        help="Force a full rebuild even if an existing index is found.",
    )
    build_parser.add_argument(
        "--no-embeddings",
        action="store_true",
        dest="no_embeddings",
        help="Disable hybrid embedding-based linking (symbol-match only, no model required).",
    )

    detect_parser = subparsers.add_parser(
        "detect",
        help="Detect doc sections that may be stale relative to a code change.",
    )
    detect_parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    detect_parser.add_argument(
        "--base",
        required=True,
        help="Base git ref (old revision).",
    )
    detect_parser.add_argument(
        "--head",
        required=True,
        help="Head git ref (new revision).",
    )
    detect_parser.add_argument(
        "--index",
        default=".docsmith/index.json",
        help="Path to the persisted index JSON (default: .docsmith/index.json).",
    )
    detect_parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="Path to the layered YAML config (default: configs/base.yaml).",
    )

    investigate_parser = subparsers.add_parser(
        "investigate",
        help="Run detection and ask an LLM to confirm which suspect sections are stale.",
    )
    investigate_parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    investigate_parser.add_argument(
        "--base",
        required=True,
        help="Base git ref (old revision).",
    )
    investigate_parser.add_argument(
        "--head",
        required=True,
        help="Head git ref (new revision).",
    )
    investigate_parser.add_argument(
        "--index",
        default=".docsmith/index.json",
        help="Path to the persisted index JSON (default: .docsmith/index.json).",
    )
    investigate_parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="Path to the layered YAML config (default: configs/base.yaml).",
    )
    investigate_parser.add_argument(
        "--backend",
        choices=["fake", "ollama", "claude"],
        default=None,
        help="LLM backend to use (default: from config).",
    )
    investigate_parser.add_argument(
        "--model",
        default=None,
        help="Model name override for the selected backend (default: from config).",
    )

    repair_parser = subparsers.add_parser(
        "repair",
        help="Propose doc corrections for stale sections and route them by confidence.",
    )
    repair_parser.add_argument("--repo", default=".", help="Repository root (default: cwd).")
    repair_parser.add_argument("--base", required=True, help="Base git ref (old revision).")
    repair_parser.add_argument("--head", required=True, help="Head git ref (new revision).")
    repair_parser.add_argument(
        "--index",
        default=".docsmith/index.json",
        help="Path to the persisted index JSON (default: .docsmith/index.json).",
    )
    repair_parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="Path to the layered YAML config (default: configs/base.yaml).",
    )
    repair_parser.add_argument(
        "--backend",
        choices=["fake", "ollama", "claude"],
        default=None,
        help="LLM backend to use (default: from config).",
    )
    repair_parser.add_argument(
        "--model", default=None, help="Model override for the selected backend."
    )
    repair_parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the AUTOFIX confidence threshold (default: from config).",
    )

    action_parser = subparsers.add_parser(
        "github-action",
        help="Run Docsmith as a GitHub Action on the current pull request.",
    )
    action_parser.add_argument(
        "--repo",
        default=".",
        help="Path to the checked-out repository (default: current directory).",
    )

    args = parser.parse_args()

    if args.subcommand == "build-index":
        embeddings = not args.no_embeddings
        index_exists = os.path.exists(args.output)

        if args.full or not index_exists:
            index = build_index(
                args.repo,
                output_path=args.output,
                embeddings=embeddings,
                full=args.full,
            )
        else:
            index = update_index(args.repo, args.output, embeddings=embeddings)

        n_symbols = len(index.symbols)
        n_sections = len(index.sections)
        n_links = len(index.links)
        print(
            f"Indexed {n_symbols} symbols, {n_sections} sections,"
            f" {n_links} links -> {args.output}"
        )

    elif args.subcommand == "detect":
        settings = load_settings(args.config)
        result = detect(args.repo, args.base, args.head, args.index, settings)

        n_changed = len(result.changed_symbols)
        n_suspects = len(result.suspects)
        n_dropped = sum(result.dropped.values())
        print(
            f"Detected {n_changed} changed symbols, {n_suspects} suspect sections"
            f" ({n_dropped} dropped)"
        )

        index = load_index(args.index)
        suspects_by_file: dict[str, list] = {}
        for suspect in result.suspects:
            section = index.sections.get(suspect.section_id)
            doc_file = section.file if section is not None else "<unknown>"
            suspects_by_file.setdefault(doc_file, []).append(suspect)

        for doc_file in sorted(suspects_by_file):
            print(f"{doc_file}:")
            file_suspects = sorted(suspects_by_file[doc_file], key=lambda s: s.section_id)
            for suspect in file_suspects:
                print(f"  - {suspect.section_id} (via {suspect.via}, {suspect.change_kind.value})")

    elif args.subcommand == "investigate":
        settings = load_settings(args.config)

        if args.model:
            effective_backend = args.backend or settings.llm_backend
            if effective_backend == "claude":
                settings.claude_model = args.model
            else:
                settings.ollama_model = args.model

        client = make_client(settings, backend_override=args.backend)
        try:
            result = investigate_pr(args.repo, args.base, args.head, args.index, settings, client)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        for verdict in result.verdicts:
            symbol_name = verdict.symbol_id.split("::")[-1].rsplit(".", 1)[-1]
            if verdict.stale:
                print(f"STALE ({verdict.confidence:.2f}) {verdict.section_id} — {symbol_name}")
                for claim in verdict.wrong_claims:
                    print(f"  - {claim}")
            else:
                print(f"OK          {verdict.section_id} — {symbol_name}")

        if result.skipped:
            n_skipped = sum(result.skipped.values())
            print(f"({n_skipped} skipped)")

    elif args.subcommand == "repair":
        settings = load_settings(args.config)

        if args.model:
            effective_backend = args.backend or settings.llm_backend
            if effective_backend == "claude":
                settings.claude_model = args.model
            else:
                settings.ollama_model = args.model
        if args.threshold is not None:
            settings.repair_confidence_threshold = args.threshold

        client = make_client(settings, backend_override=args.backend)
        try:
            result = repair_pr(args.repo, args.base, args.head, args.index, settings, client)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

        n_auto = n_flag = n_nochange = 0
        for outcome in result.outcomes:
            proposal = outcome.proposal
            symbol_name = proposal.symbol_id.split("::")[-1].rsplit(".", 1)[-1]
            if outcome.route is RepairRoute.NO_CHANGE:
                n_nochange += 1
                continue
            label = "AUTOFIX " if outcome.route is RepairRoute.AUTOFIX else "FLAG    "
            if outcome.route is RepairRoute.AUTOFIX:
                n_auto += 1
            else:
                n_flag += 1
            print(f"{label} {proposal.section_id} — {symbol_name}   ({outcome.reason})")
            for line in proposal.diff.splitlines():
                print(f"  {line}")

        n_skipped = sum(result.skipped.values())
        print(
            f"{n_auto} auto-fixable · {n_flag} flagged · "
            f"{n_nochange} unchanged · {n_skipped} skipped"
        )

    elif args.subcommand == "github-action":
        counts = run_action(os.environ, args.repo)
        output_path = os.environ.get("GITHUB_OUTPUT")
        lines = [
            f"verified={counts.verified}",
            f"fixed={counts.fixed}",
            f"flagged={counts.flagged}",
            f"fix-pr-url={counts.fix_pr_url or ''}",
        ]
        if output_path:
            with open(output_path, "a") as fh:
                fh.write("\n".join(lines) + "\n")
        print(
            f"Docsmith: {counts.verified} verified, {counts.fixed} auto-fixed, "
            f"{counts.flagged} flagged"
        )


if __name__ == "__main__":
    main()
