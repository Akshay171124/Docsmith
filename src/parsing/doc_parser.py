"""Split docs into sections by heading and extract referenced symbols and config keys.

Covers markdown/README, docstrings/JSDoc, API reference, and config/CLI/env docs.
"""

from __future__ import annotations

import re

from src.models import DocSection

# Matches ATX headings: group 1 = hashes, group 2 = heading text (trailing # stripped)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")

# Matches inline-code spans (content between single backticks)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# All-caps config-key pattern: starts with A-Z, then 2+ chars of A-Z, 0-9, or _
_CONFIG_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")

# Valid Python/JS identifier
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _slug(text: str) -> str:
    """Lowercase text and replace runs of non-alphanumeric chars with a single '-'.

    Args:
        text: The heading text to slugify.

    Returns:
        A URL-safe slug string with no leading or trailing hyphens.
    """
    lowered = text.lower()
    slugified = re.sub(r"[^a-z0-9]+", "-", lowered)
    return slugified.strip("-")


def _extract_references(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Scan inline-code spans and classify each token as a symbol or config key.

    Tokens between single backticks are extracted, then tested in order:
    1. ALL-CAPS config-key pattern (``^[A-Z][A-Z0-9_]{2,}$``) → config key.
    2. Valid identifier pattern (``^[A-Za-z_][A-Za-z0-9_]*$``) → symbol.
    Tokens matching neither are ignored. Each list is de-duplicated preserving
    first-seen order.

    Args:
        text: The raw section body text to scan for references.

    Returns:
        A 2-tuple of (referenced_symbols, referenced_config_keys).
    """
    symbols: dict[str, None] = {}
    config_keys: dict[str, None] = {}

    for match in _INLINE_CODE_RE.finditer(text):
        token = match.group(1).strip()
        if _CONFIG_KEY_RE.match(token):
            config_keys[token] = None
        elif _IDENTIFIER_RE.match(token):
            symbols[token] = None

    return tuple(symbols), tuple(config_keys)


def parse_markdown(path: str) -> list[DocSection]:
    """Parse a markdown file into heading-delimited DocSection objects.

    Content before the first heading is ignored. Each heading starts a new section
    that runs up to (but not including) the next heading, or to the end of file.

    Args:
        path: Filesystem path to the markdown file.

    Returns:
        A list of DocSection objects, one per ATX heading found in the file.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    # Collect (1-based line number, heading text) for every ATX heading
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line.rstrip("\n"))
        if match:
            headings.append((i, match.group(2)))

    sections: list[DocSection] = []
    for idx, (heading_lineno, heading_text) in enumerate(headings):
        # Section body starts on the line after the heading
        body_start = heading_lineno  # 0-based index into lines = heading_lineno - 1 + 1
        # Section ends at the line before the next heading, or EOF
        if idx + 1 < len(headings):
            next_heading_lineno = headings[idx + 1][0]
            end_lineno = next_heading_lineno - 1
        else:
            end_lineno = len(lines)

        # raw = lines after the heading up to end_lineno (inclusive), joined
        body_lines = lines[body_start:end_lineno]  # body_start is already 0-based end
        raw = "".join(body_lines)

        symbols, config_keys = _extract_references(raw)

        sections.append(
            DocSection(
                id=f"{path}#{_slug(heading_text)}",
                heading_path=(heading_text,),
                file=path,
                raw=raw,
                start_line=heading_lineno,
                end_line=end_lineno,
                referenced_symbols=symbols,
                referenced_config_keys=config_keys,
            )
        )

    return sections
