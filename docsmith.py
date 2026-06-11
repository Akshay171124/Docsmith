"""Docsmith entry point.

Single CLI entry (mirrors Forge's `forge.py`) usable both locally and inside the
GitHub Action:

    python docsmith.py --repo . --base main --head HEAD      # local run
    python docsmith.py --github-action                       # CI run (reads event ctx)

Local mode is for development and the evaluation harness; --github-action mode reads
the PR context from the Actions environment and posts results back to GitHub.
"""

# TODO(impl): wire argparse + dispatch into src/ pipeline per
#             docs/superpowers/specs/2026-06-11-self-healing-docs-design.md


def main() -> None:
    raise NotImplementedError("Docsmith entry point not yet implemented.")


if __name__ == "__main__":
    main()
