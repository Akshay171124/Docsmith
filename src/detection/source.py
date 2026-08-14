"""Extract a code symbol's source text from in-memory file content.

Shared by the staleness investigator and the repair engine so both slice a
changed symbol's source the same way.
"""

from __future__ import annotations

from src.parsing.code_parser import parse_source
from src.parsing.languages import language_for_path


def extract_symbol_source(content: str | None, file: str, qualified_name: str) -> str | None:
    """Extract a symbol's source text from full file content by re-parsing.

    Args:
        content: Full file content, or None if the file didn't exist at this revision.
        file: Repo-relative path of the file (used to resolve the language).
        qualified_name: Fully qualified name of the symbol to extract.

    Returns:
        The symbol's source lines (1-based, inclusive), or None if `content` is
        None, the language is unsupported, or the symbol isn't found.
    """
    if content is None:
        return None

    language = language_for_path(file)
    if language is None:
        return None

    symbols = parse_source(content, file, language)
    symbol = next((s for s in symbols if s.qualified_name == qualified_name), None)
    if symbol is None:
        return None

    lines = content.splitlines()
    return "\n".join(lines[symbol.start_line - 1 : symbol.end_line])
