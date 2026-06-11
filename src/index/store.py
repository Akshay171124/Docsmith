"""Persist/load the index (symbols, doc sections, links) as JSON in .docsmith/."""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any

from src.models import DocSection, Index, Link, Symbol

# Fields on DocSection that are tuples and must survive the JSON list→tuple round-trip.
_DOCSECTION_TUPLE_FIELDS = ("heading_path", "referenced_symbols", "referenced_config_keys")


def _section_from_dict(data: dict[str, Any]) -> DocSection:
    """Reconstruct a DocSection from a plain dict, restoring tuples.

    Args:
        data: Dict produced by json.load for a single section entry.

    Returns:
        A fully reconstructed, frozen DocSection with tuple fields as tuples.
    """
    fixed = {
        key: tuple(value) if key in _DOCSECTION_TUPLE_FIELDS else value
        for key, value in data.items()
    }
    return DocSection(**fixed)


def save_index(index: Index, path: str) -> None:
    """Write the index to a JSON file, creating parent directories as needed.

    The JSON has three top-level keys: ``"symbols"``, ``"sections"``, and ``"links"``.
    Tuple fields on DocSection are stored as JSON arrays.

    Args:
        index: The Index to persist.
        path: Filesystem path for the output file (e.g. ``.docsmith/index.json``).
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    payload: dict[str, Any] = {
        "symbols": {sid: dataclasses.asdict(sym) for sid, sym in index.symbols.items()},
        "sections": {sec_id: dataclasses.asdict(sec) for sec_id, sec in index.sections.items()},
        "links": [dataclasses.asdict(link) for link in index.links],
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_index(path: str) -> Index:
    """Load an index from a JSON file previously written by ``save_index``.

    Restores all dataclasses exactly, including tuple fields on DocSection.

    Args:
        path: Filesystem path of the JSON file to read.

    Returns:
        A fully reconstructed Index with all symbols, sections, and links.
    """
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)

    symbols = {sid: Symbol(**data) for sid, data in payload["symbols"].items()}
    sections = {sec_id: _section_from_dict(data) for sec_id, data in payload["sections"].items()}
    links = [Link(**data) for data in payload["links"]]

    return Index(symbols=symbols, sections=sections, links=links)
