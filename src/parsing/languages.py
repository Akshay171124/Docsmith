"""Per-language tree-sitter grammar config and symbol-extraction queries."""

from __future__ import annotations

import os

# Maps lowercase file extension (including the dot) to a tree-sitter language name.
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
}

# Sorted unique list of supported language names derived from the extension map.
SUPPORTED_LANGUAGES: list[str] = sorted(set(_EXT_TO_LANGUAGE.values()))

# One tree-sitter S-expression query per language.
# Each query captures a definition node as @def and its name node as @name.
# These capture names are required by the code parser in the next task.
SYMBOL_QUERIES: dict[str, str] = {
    "python": """
        (function_definition name: (identifier) @name) @def
        (class_definition name: (identifier) @name) @def
    """,
    "typescript": """
        (function_declaration name: (identifier) @name) @def
        (class_declaration name: (type_identifier) @name) @def
        (method_definition name: (property_identifier) @name) @def
    """,
    "javascript": """
        (function_declaration name: (identifier) @name) @def
        (class_declaration name: (identifier) @name) @def
        (method_definition name: (property_identifier) @name) @def
    """,
    "go": """
        (function_declaration name: (identifier) @name) @def
        (method_declaration name: (field_identifier) @name) @def
        (type_declaration (type_spec name: (type_identifier) @name)) @def
    """,
}


def language_for_path(path: str) -> str | None:
    """Return the tree-sitter language name for the given file path.

    Args:
        path: File path (relative or absolute). Only the extension is used.

    Returns:
        A language name string (e.g. "python") if the extension is supported,
        or None for unsupported or missing extensions.
    """
    _, ext = os.path.splitext(path)
    if not ext:
        return None
    return _EXT_TO_LANGUAGE.get(ext.lower())
