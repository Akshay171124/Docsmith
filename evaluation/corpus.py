"""Load the bundled curated evaluation corpus (one JSON file per case)."""

from __future__ import annotations

import glob
import json
import os

from evaluation.models import Case, Gold


def load_curated_cases(root: str = "evaluation/data/curated") -> list[Case]:
    """Load every ``*.json`` case file under ``root`` into a Case, sorted by id.

    Args:
        root: Directory holding curated case JSON files.

    Returns:
        The loaded cases, ordered by ``case_id``.
    """
    cases: list[Case] = []
    for path in sorted(glob.glob(os.path.join(root, "*.json"))):
        with open(path) as fh:
            raw = json.load(fh)
        gold = raw["gold"]
        cases.append(
            Case(
                case_id=raw["case_id"],
                base_files=raw["base_files"],
                head_files=raw["head_files"],
                gold=Gold(
                    stale_section_ids=frozenset(gold.get("stale_section_ids", [])),
                    fixes=gold.get("fixes", {}),
                ),
            )
        )
    return cases
