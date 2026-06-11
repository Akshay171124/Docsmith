"""Extract code symbols (functions, classes, methods) via tree-sitter."""

from __future__ import annotations

from tree_sitter_languages import get_language, get_parser

from src.models import Symbol
from src.parsing.languages import SYMBOL_QUERIES, language_for_path

_CLASS_TYPES = frozenset({"class_definition", "class_declaration", "type_declaration"})
_METHOD_TYPES = frozenset({"method_definition", "method_declaration"})


def parse_file(path: str) -> list[Symbol]:
    """Parse a source file and return all extracted symbols.

    Args:
        path: Absolute or relative path to the source file.

    Returns:
        A list of Symbol objects for each definition found,
        or an empty list for unsupported file types.
    """
    language = language_for_path(path)
    if language is None:
        return []

    with open(path, "rb") as fh:
        source = fh.read()

    tree = get_parser(language).parse(source)
    query = get_language(language).query(SYMBOL_QUERIES[language])
    captures = query.captures(tree.root_node)

    def_nodes = [node for node, cap in captures if cap == "def"]
    name_nodes = [node for node, cap in captures if cap == "name"]

    symbols: list[Symbol] = []
    for name_node in name_nodes:
        def_node = _smallest_containing_def(name_node, def_nodes)
        if def_node is None:
            continue
        symbols.append(_build_symbol(path, language, source, def_node, name_node))

    return symbols


def _smallest_containing_def(name_node, def_nodes):
    """Return the smallest def_node whose byte range contains name_node.

    Args:
        name_node: The tree-sitter node for the symbol name.
        def_nodes: All captured definition nodes.

    Returns:
        The containing def node with the tightest span, or None.
    """
    best = None
    best_span = None
    for d in def_nodes:
        if d.start_byte <= name_node.start_byte and name_node.end_byte <= d.end_byte:
            span = d.end_byte - d.start_byte
            if best_span is None or span < best_span:
                best = d
                best_span = span
    return best


def _class_ancestor(node):
    """Walk ancestors looking for a class_definition or class_declaration node.

    Args:
        node: Starting tree-sitter node.

    Returns:
        The first ancestor class node found, or None.
    """
    current = node.parent
    while current is not None:
        if current.type in ("class_definition", "class_declaration"):
            return current
        current = current.parent
    return None


def _class_name(class_node, source: bytes) -> str:
    """Extract the class name from a class definition node.

    Args:
        class_node: A class_definition or class_declaration tree-sitter node.
        source: Raw source bytes of the file.

    Returns:
        The class name as a string.
    """
    for child in class_node.children:
        if child.type in ("identifier", "type_identifier"):
            return source[child.start_byte : child.end_byte].decode("utf-8")
    return ""


def _qualified_name(def_node, name: str, source: bytes) -> str:
    """Compute the qualified name for a symbol.

    If the def_node is nested inside a class, prefix with ClassName.

    Args:
        def_node: The definition tree-sitter node.
        name: The simple symbol name.
        source: Raw source bytes of the file.

    Returns:
        Qualified name string, e.g. "MyClass.my_method" or "my_function".
    """
    class_node = _class_ancestor(def_node)
    if class_node is not None:
        cls = _class_name(class_node, source)
        return f"{cls}.{name}" if cls else name
    return name


def _kind_for(def_node, qualified_name: str) -> str:
    """Determine the symbol kind from its def node type and qualified name.

    Args:
        def_node: The definition tree-sitter node.
        qualified_name: The fully-qualified symbol name.

    Returns:
        One of "class", "method", or "function".
    """
    node_type = def_node.type
    if node_type in _CLASS_TYPES:
        return "class"
    if node_type in _METHOD_TYPES or "." in qualified_name:
        return "method"
    return "function"


def _first_line(def_node, source: bytes) -> str:
    """Return the first line of the def node's source text, right-stripped.

    Args:
        def_node: The definition tree-sitter node.
        source: Raw source bytes of the file.

    Returns:
        The first line of the definition, right-stripped.
    """
    text = source[def_node.start_byte : def_node.end_byte].decode("utf-8")
    return text.splitlines()[0].rstrip()


def _docstring(def_node, source: bytes, language: str) -> str | None:
    """Extract the docstring from a definition node (Python only).

    Looks for: def_node -> block -> first expression_statement -> string child.

    Args:
        def_node: The definition tree-sitter node.
        source: Raw source bytes of the file.
        language: The language name.

    Returns:
        The docstring text with surrounding quotes and whitespace stripped,
        or None if absent or language is not Python.
    """
    if language != "python":
        return None

    block = next((c for c in def_node.children if c.type == "block"), None)
    if block is None:
        return None

    first_stmt = next((c for c in block.children if c.type == "expression_statement"), None)
    if first_stmt is None:
        return None

    string_node = next((c for c in first_stmt.children if c.type == "string"), None)
    if string_node is None:
        return None

    raw = source[string_node.start_byte : string_node.end_byte].decode("utf-8")
    # Strip triple-quote or single-quote delimiters and surrounding whitespace.
    for quote in ('"""', "'''", '"', "'"):
        if raw.startswith(quote) and raw.endswith(quote) and len(raw) >= 2 * len(quote):
            raw = raw[len(quote) : -len(quote)]
            break
    return raw.strip()


def _build_symbol(
    path: str,
    language: str,
    source: bytes,
    def_node,
    name_node,
) -> Symbol:
    """Construct a Symbol from the parsed nodes.

    Args:
        path: Source file path.
        language: Tree-sitter language name.
        source: Raw source bytes of the file.
        def_node: The definition tree-sitter node.
        name_node: The name tree-sitter node.

    Returns:
        A fully-populated Symbol dataclass instance.
    """
    name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
    qname = _qualified_name(def_node, name, source)
    kind = _kind_for(def_node, qname)
    return Symbol(
        id=f"{path}::{qname}",
        name=name,
        qualified_name=qname,
        kind=kind,
        signature=_first_line(def_node, source),
        docstring=_docstring(def_node, source, language),
        file=path,
        start_line=def_node.start_point[0] + 1,
        end_line=def_node.end_point[0] + 1,
        language=language,
    )
