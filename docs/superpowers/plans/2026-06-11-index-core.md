# Index Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persisted, queryable code↔docs index — parse a repository into code symbols (tree-sitter, multi-language) and documentation sections (markdown + docstrings), link them deterministically by name, and serialize the result to `.docsmith/index.json`.

**Architecture:** Pure, deterministic, zero-LLM. A `parsing` layer turns source files into `Symbol`s and doc files into `DocSection`s. A `builder` walks a repo, runs both parsers, and links sections to symbols by name match. A `store` serializes the `Index` to JSON and reads it back. Everything is a pure function over inputs, so the whole subsystem is unit-testable with fixtures. (Embeddings and incremental updates are deliberately deferred to the Week 2 "Retrieval layer" plan.)

**Tech Stack:** Python 3.11, `tree-sitter` + `tree-sitter-languages` (pinned), `pytest`. No network, no API keys.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/models.py` (create) | Core dataclasses: `Symbol`, `DocSection`, `Link`, `Index`. Pure data, no logic. |
| `src/parsing/languages.py` (modify stub) | Map file → language; hold per-language tree-sitter symbol queries. |
| `src/parsing/code_parser.py` (modify stub) | Extract `Symbol`s from a source file via tree-sitter. |
| `src/parsing/doc_parser.py` (modify stub) | Split docs into `DocSection`s; extract referenced symbol/config names. |
| `src/index/linker.py` (create) | Deterministic symbol↔section linking by name. |
| `src/index/store.py` (modify stub) | Serialize/deserialize `Index` ⇄ JSON. |
| `src/index/builder.py` (modify stub) | Walk a repo, parse code + docs, link, return `Index`. |
| `docsmith.py` (modify stub) | `build-index` CLI subcommand to make the subsystem runnable. |
| `tests/fixtures/sample_repo/` (create) | Tiny multi-language repo used across tests. |
| `tests/unit/test_*.py` (create) | One test module per source module. |
| `tests/integration/test_build_index.py` (create) | End-to-end build over the fixture repo. |

---

## Task 0: Pin dependencies and create the fixture repo

**Files:**
- Modify: `requirements.txt`
- Create: `tests/fixtures/sample_repo/app.py`
- Create: `tests/fixtures/sample_repo/service.ts`
- Create: `tests/fixtures/sample_repo/README.md`

- [ ] **Step 1: Pin tree-sitter versions**

`tree-sitter-languages` 1.10.x requires `tree-sitter` 0.21.x. Replace the two parsing lines in `requirements.txt` with exact pins:

```
# --- parsing ---
tree-sitter==0.21.3
tree-sitter-languages==1.10.2
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: installs without resolver conflicts; `python -c "from tree_sitter_languages import get_parser; get_parser('python')"` prints nothing and exits 0.

- [ ] **Step 3: Create `tests/fixtures/sample_repo/app.py`**

```python
"""Example application module."""


def create_user(name: str, email: str) -> dict:
    """Create a user record.

    Args:
        name: The user's display name.
        email: The user's email address.
    Returns:
        A dict with the new user's fields.
    """
    return {"name": name, "email": email}


class UserService:
    """Manages user lifecycle."""

    def deactivate(self, user_id: int) -> bool:
        """Deactivate a user by id."""
        return True
```

- [ ] **Step 4: Create `tests/fixtures/sample_repo/service.ts`**

```typescript
export function formatName(first: string, last: string): string {
  return `${first} ${last}`;
}

export class Cache {
  get(key: string): string | null {
    return null;
  }
}
```

- [ ] **Step 5: Create `tests/fixtures/sample_repo/README.md`**

```markdown
# Sample App

## Users

Use `create_user` to make a user. The `UserService` class manages lifecycle;
call `deactivate` to disable an account.

## Formatting

`formatName` joins a first and last name.

## Config

Set the `MAX_USERS` environment variable to cap account creation.
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/fixtures/sample_repo
git commit -m "test: pin tree-sitter and add sample fixture repo"
```

---

## Task 1: Core data models

**Files:**
- Create: `src/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_models.py
from src.models import Symbol, DocSection, Link, Index


def test_symbol_is_hashable_and_carries_location():
    sym = Symbol(
        id="app.py::create_user",
        name="create_user",
        qualified_name="create_user",
        kind="function",
        signature="def create_user(name: str, email: str) -> dict:",
        docstring="Create a user record.",
        file="app.py",
        start_line=4,
        end_line=14,
        language="python",
    )
    assert sym.name == "create_user"
    assert {sym}  # frozen dataclass is hashable


def test_index_holds_collections_keyed_by_id():
    idx = Index(symbols={}, sections={}, links=[])
    assert idx.symbols == {}
    assert idx.links == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/models.py
"""Core data models for the Docsmith index. Pure data, no logic."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Symbol:
    """A code unit extracted from a source file."""

    id: str               # stable identifier, e.g. "path/app.py::UserService.deactivate"
    name: str             # bare name, e.g. "deactivate"
    qualified_name: str   # dotted name within the file, e.g. "UserService.deactivate"
    kind: str             # function | class | method
    signature: str        # the definition line(s)
    docstring: str | None
    file: str
    start_line: int
    end_line: int
    language: str


@dataclass(frozen=True)
class DocSection:
    """A documentation section delimited by a heading."""

    id: str                          # "README.md#users" (file + slugified heading path)
    heading_path: tuple[str, ...]    # ("Users",) or ("Config", "Env Vars")
    file: str
    raw: str
    start_line: int
    end_line: int
    referenced_symbols: tuple[str, ...]
    referenced_config_keys: tuple[str, ...]


@dataclass(frozen=True)
class Link:
    """An edge between a code symbol and a doc section."""

    symbol_id: str
    section_id: str
    via: str            # "symbol-match" | "embedding" | "both"
    score: float


@dataclass
class Index:
    """The complete code↔docs index for a repository."""

    symbols: dict[str, Symbol] = field(default_factory=dict)
    sections: dict[str, DocSection] = field(default_factory=dict)
    links: list[Link] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/unit/test_models.py
git commit -m "feat: add core index data models"
```

---

## Task 2: Language registry

**Files:**
- Modify: `src/parsing/languages.py`
- Test: `tests/unit/test_languages.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_languages.py
import pytest

from src.parsing.languages import language_for_path, SYMBOL_QUERIES, SUPPORTED_LANGUAGES


def test_language_for_path_maps_known_extensions():
    assert language_for_path("a/b/app.py") == "python"
    assert language_for_path("service.ts") == "typescript"
    assert language_for_path("m.js") == "javascript"
    assert language_for_path("main.go") == "go"


def test_language_for_path_returns_none_for_unknown():
    assert language_for_path("notes.txt") is None
    assert language_for_path("Makefile") is None


def test_every_supported_language_has_a_query():
    for lang in SUPPORTED_LANGUAGES:
        assert lang in SYMBOL_QUERIES
        assert SYMBOL_QUERIES[lang].strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_languages.py -v`
Expected: FAIL with `ImportError: cannot import name 'language_for_path'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parsing/languages.py
"""Per-language tree-sitter grammar config and symbol-extraction queries."""

from __future__ import annotations

import os

# Map file extension -> tree-sitter language name.
_EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
}

SUPPORTED_LANGUAGES = sorted(set(_EXTENSION_TO_LANGUAGE.values()))

# tree-sitter S-expression queries. Each captures a definition node as @def and its
# name node as @name. The parser uses these capture names; do not rename them.
SYMBOL_QUERIES = {
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
    """Return the tree-sitter language name for a file path, or None if unsupported."""
    _, ext = os.path.splitext(path)
    return _EXTENSION_TO_LANGUAGE.get(ext.lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_languages.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/parsing/languages.py tests/unit/test_languages.py
git commit -m "feat: add language registry and symbol queries"
```

---

## Task 3: Code parser — Python symbols with docstrings

**Files:**
- Modify: `src/parsing/code_parser.py`
- Test: `tests/unit/test_code_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_code_parser.py
from pathlib import Path

from src.parsing.code_parser import parse_file

FIXTURE = Path("tests/fixtures/sample_repo")


def test_parse_python_extracts_function_class_and_method():
    symbols = parse_file(str(FIXTURE / "app.py"))
    names = {s.name for s in symbols}
    assert {"create_user", "UserService", "deactivate"} <= names


def test_parse_python_captures_docstring_and_signature():
    symbols = {s.name: s for s in parse_file(str(FIXTURE / "app.py"))}
    cu = symbols["create_user"]
    assert cu.kind == "function"
    assert cu.signature.startswith("def create_user(")
    assert cu.docstring is not None and "Create a user record" in cu.docstring
    assert cu.language == "python"
    assert cu.start_line >= 1


def test_parse_python_qualifies_method_with_class():
    symbols = {s.qualified_name: s for s in parse_file(str(FIXTURE / "app.py"))}
    assert "UserService.deactivate" in symbols
    assert symbols["UserService.deactivate"].kind == "method"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_code_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_file'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parsing/code_parser.py
"""Extract code symbols (functions, classes, methods) from a source file via tree-sitter."""

from __future__ import annotations

from tree_sitter_languages import get_language, get_parser

from src.models import Symbol
from src.parsing.languages import SYMBOL_QUERIES, language_for_path


def parse_file(path: str) -> list[Symbol]:
    """Parse one source file into a list of Symbols.

    Args:
        path: Path to the source file.
    Returns:
        Symbols found in the file. Empty list if the language is unsupported.
    """
    language = language_for_path(path)
    if language is None:
        return []

    with open(path, "rb") as fh:
        source = fh.read()

    parser = get_parser(language)
    tree = parser.parse(source)
    query = get_language(language).query(SYMBOL_QUERIES[language])

    # Collect captured definition nodes and name nodes, then pair each name with the
    # SMALLEST definition node that contains it. This is robust to nesting (a method's
    # name is contained by both its class node and its method node — the method wins).
    def_nodes = []
    name_nodes = []
    for node, capture in query.captures(tree.root_node):
        if capture == "def":
            def_nodes.append(node)
        elif capture == "name":
            name_nodes.append(node)

    symbols: list[Symbol] = []
    for name_node in name_nodes:
        container = _smallest_containing_def(name_node, def_nodes)
        if container is None:
            continue
        symbols.append(_build_symbol(container, name_node, source, path, language))
    return symbols


def _smallest_containing_def(name_node, def_nodes):
    """Return the smallest captured @def node whose byte range contains name_node."""
    best = None
    for d in def_nodes:
        if d.start_byte <= name_node.start_byte and name_node.end_byte <= d.end_byte:
            if best is None or (d.end_byte - d.start_byte) < (best.end_byte - best.start_byte):
                best = d
    return best


def _build_symbol(def_node, name_node, source: bytes, path: str, language: str) -> Symbol:
    name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")
    qualified = _qualified_name(def_node, name, source)
    kind = _kind_for(def_node.type, qualified)
    signature = _first_line(source, def_node)
    docstring = _docstring(def_node, source, language)
    return Symbol(
        id=f"{path}::{qualified}",
        name=name,
        qualified_name=qualified,
        kind=kind,
        signature=signature,
        docstring=docstring,
        file=path,
        start_line=def_node.start_point[0] + 1,
        end_line=def_node.end_point[0] + 1,
        language=language,
    )


def _qualified_name(def_node, name: str, source: bytes) -> str:
    """Prefix with an enclosing class name when the def sits inside one."""
    parent = def_node.parent
    while parent is not None:
        if parent.type in ("class_definition", "class_declaration"):
            for child in parent.children:
                if child.type in ("identifier", "type_identifier"):
                    cls = source[child.start_byte : child.end_byte].decode("utf-8")
                    return f"{cls}.{name}"
        parent = parent.parent
    return name


def _kind_for(node_type: str, qualified: str) -> str:
    if "class" in node_type or "type_declaration" in node_type or "type_spec" in node_type:
        return "class"
    if "." in qualified or "method" in node_type:
        return "method"
    return "function"


def _first_line(source: bytes, def_node) -> str:
    text = source[def_node.start_byte : def_node.end_byte].decode("utf-8")
    return text.splitlines()[0].rstrip()


def _docstring(def_node, source: bytes, language: str) -> str | None:
    """Best-effort docstring extraction (Python only for now)."""
    if language != "python":
        return None
    body = next((c for c in def_node.children if c.type == "block"), None)
    if body is None:
        return None
    first = next((c for c in body.children if c.type == "expression_statement"), None)
    if first is None:
        return None
    string_node = next((c for c in first.children if c.type == "string"), None)
    if string_node is None:
        return None
    raw = source[string_node.start_byte : string_node.end_byte].decode("utf-8")
    return raw.strip().strip('"').strip("'").strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_code_parser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/parsing/code_parser.py tests/unit/test_code_parser.py
git commit -m "feat: extract Python symbols with docstrings via tree-sitter"
```

---

## Task 4: Code parser — TypeScript, JavaScript, Go

**Files:**
- Test: `tests/unit/test_code_parser_multilang.py`

(No source change expected — the parser is already language-driven. This task proves it and fixes anything language-specific that surfaces.)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_code_parser_multilang.py
from pathlib import Path

from src.parsing.code_parser import parse_file

FIXTURE = Path("tests/fixtures/sample_repo")


def test_parse_typescript_extracts_function_and_class():
    symbols = {s.name: s for s in parse_file(str(FIXTURE / "service.ts"))}
    assert "formatName" in symbols
    assert symbols["formatName"].language == "typescript"
    assert "Cache" in symbols
    assert symbols["Cache"].kind == "class"


def test_unsupported_extension_returns_empty():
    assert parse_file(str(FIXTURE / "README.md")) == []
```

- [ ] **Step 2: Run test to verify it fails (or surfaces a bug)**

Run: `pytest tests/unit/test_code_parser_multilang.py -v`
Expected: Initially may FAIL if a query capture name differs per grammar. If it passes immediately, that is acceptable — proceed to Step 4.

- [ ] **Step 3: Fix only if needed**

If a language's query raised a `QueryError`, adjust that language's entry in `src/parsing/languages.py::SYMBOL_QUERIES` to match the grammar's node names (e.g. TypeScript class names are `type_identifier`, already handled). Make the minimal change and re-run.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_code_parser_multilang.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_code_parser_multilang.py src/parsing/languages.py
git commit -m "test: verify multi-language symbol extraction"
```

---

## Task 5: Doc parser — split into sections

**Files:**
- Modify: `src/parsing/doc_parser.py`
- Test: `tests/unit/test_doc_parser_sections.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_doc_parser_sections.py
from pathlib import Path

from src.parsing.doc_parser import parse_markdown

FIXTURE = Path("tests/fixtures/sample_repo/README.md")


def test_parse_markdown_splits_by_heading():
    sections = parse_markdown(str(FIXTURE))
    headings = {s.heading_path for s in sections}
    assert ("Sample App",) in headings
    assert ("Users",) in headings
    assert ("Formatting",) in headings
    assert ("Config",) in headings


def test_section_captures_raw_body_and_line_span():
    sections = {s.heading_path: s for s in parse_markdown(str(FIXTURE))}
    users = sections[("Users",)]
    assert "create_user" in users.raw
    assert users.start_line < users.end_line
    assert users.file.endswith("README.md")
    assert users.id == "tests/fixtures/sample_repo/README.md#users"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_doc_parser_sections.py -v`
Expected: FAIL with `ImportError: cannot import name 'parse_markdown'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/parsing/doc_parser.py
"""Split docs into sections by heading and extract referenced code/config names.

Covers markdown/README (heading-delimited sections). Docstring/JSDoc, API-reference,
and config/CLI extractors layer on in later plans.
"""

from __future__ import annotations

import re

from src.models import DocSection

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONFIG_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")  # e.g. MAX_USERS


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_markdown(path: str) -> list[DocSection]:
    """Parse a markdown file into one DocSection per heading.

    Args:
        path: Path to the markdown file.
    Returns:
        Sections in document order. Content before the first heading is ignored.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    sections: list[DocSection] = []
    current: dict | None = None

    def flush(end_line: int) -> None:
        if current is None:
            return
        raw = "".join(current["body"])
        refs, keys = _extract_references(raw)
        sections.append(
            DocSection(
                id=f"{path}#{_slug(current['heading'])}",
                heading_path=(current["heading"],),
                file=path,
                raw=raw,
                start_line=current["start_line"],
                end_line=end_line,
                referenced_symbols=refs,
                referenced_config_keys=keys,
            )
        )

    for i, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match:
            flush(end_line=i - 1)
            current = {"heading": match.group(2), "start_line": i, "body": []}
        elif current is not None:
            current["body"].append(line)
    flush(end_line=len(lines))
    return sections


def _extract_references(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Pull referenced symbol names and config keys from inline-code spans."""
    symbols: list[str] = []
    config_keys: list[str] = []
    for token in _INLINE_CODE_RE.findall(text):
        token = token.strip()
        if _CONFIG_KEY_RE.match(token):
            config_keys.append(token)
        elif _IDENTIFIER_RE.match(token):
            symbols.append(token)
    # de-dup, preserve order
    return tuple(dict.fromkeys(symbols)), tuple(dict.fromkeys(config_keys))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_doc_parser_sections.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/parsing/doc_parser.py tests/unit/test_doc_parser_sections.py
git commit -m "feat: parse markdown into heading-delimited sections"
```

---

## Task 6: Doc parser — reference extraction edge cases

**Files:**
- Test: `tests/unit/test_doc_parser_refs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_doc_parser_refs.py
from pathlib import Path

from src.parsing.doc_parser import parse_markdown

FIXTURE = Path("tests/fixtures/sample_repo/README.md")


def test_inline_code_symbols_are_extracted():
    sections = {s.heading_path: s for s in parse_markdown(str(FIXTURE))}
    users = sections[("Users",)]
    assert "create_user" in users.referenced_symbols
    assert "UserService" in users.referenced_symbols
    assert "deactivate" in users.referenced_symbols


def test_config_keys_are_separated_from_symbols():
    sections = {s.heading_path: s for s in parse_markdown(str(FIXTURE))}
    config = sections[("Config",)]
    assert "MAX_USERS" in config.referenced_config_keys
    assert "MAX_USERS" not in config.referenced_symbols
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/unit/test_doc_parser_refs.py -v`
Expected: PASS if Task 5's `_extract_references` is correct. If `MAX_USERS` lands in symbols, the `_CONFIG_KEY_RE` check must run before the identifier check (it already does) — fix ordering if a regression appears.

- [ ] **Step 3: Fix only if needed**

No change expected. If a test fails, adjust `_extract_references` in `src/parsing/doc_parser.py` so the config-key branch is evaluated first.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_doc_parser_refs.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_doc_parser_refs.py
git commit -m "test: cover symbol vs config-key reference extraction"
```

---

## Task 7: Deterministic linker

**Files:**
- Create: `src/index/linker.py`
- Test: `tests/unit/test_linker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_linker.py
from src.models import Symbol, DocSection
from src.index.linker import link_by_name


def _symbol(name, qualified=None):
    return Symbol(
        id=f"app.py::{qualified or name}",
        name=name,
        qualified_name=qualified or name,
        kind="function",
        signature=f"def {name}():",
        docstring=None,
        file="app.py",
        start_line=1,
        end_line=2,
        language="python",
    )


def _section(refs):
    return DocSection(
        id="README.md#users",
        heading_path=("Users",),
        file="README.md",
        raw="...",
        start_line=1,
        end_line=5,
        referenced_symbols=tuple(refs),
        referenced_config_keys=(),
    )


def test_link_created_when_section_references_symbol_name():
    symbols = {s.id: s for s in [_symbol("create_user")]}
    sections = {"README.md#users": _section(["create_user"])}
    links = link_by_name(symbols, sections)
    assert len(links) == 1
    assert links[0].symbol_id == "app.py::create_user"
    assert links[0].section_id == "README.md#users"
    assert links[0].via == "symbol-match"
    assert links[0].score == 1.0


def test_no_link_when_no_name_matches():
    symbols = {s.id: s for s in [_symbol("create_user")]}
    sections = {"README.md#x": _section(["unrelated_thing"])}
    assert link_by_name(symbols, sections) == []


def test_method_links_on_bare_and_qualified_name():
    symbols = {s.id: s for s in [_symbol("deactivate", "UserService.deactivate")]}
    sections = {"README.md#u": _section(["deactivate"])}
    links = link_by_name(symbols, sections)
    assert len(links) == 1
    assert links[0].symbol_id == "app.py::UserService.deactivate"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_linker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.index.linker'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/index/linker.py
"""Deterministic symbol↔section linking by name (Week 1).

Embedding-based recall links are added by the Retrieval-layer plan; this module only
produces high-precision `via="symbol-match"` edges.
"""

from __future__ import annotations

from src.models import DocSection, Link, Symbol


def link_by_name(
    symbols: dict[str, Symbol], sections: dict[str, DocSection]
) -> list[Link]:
    """Create a Link for every (section, symbol) pair where the section names the symbol.

    A section references a symbol if the symbol's bare name appears in the section's
    referenced_symbols. Methods also match on their bare name.

    Args:
        symbols: symbol_id -> Symbol.
        sections: section_id -> DocSection.
    Returns:
        One Link per matching pair, via="symbol-match", score=1.0.
    """
    by_name: dict[str, list[Symbol]] = {}
    for sym in symbols.values():
        by_name.setdefault(sym.name, []).append(sym)

    links: list[Link] = []
    for section in sections.values():
        for ref in section.referenced_symbols:
            for sym in by_name.get(ref, []):
                links.append(
                    Link(
                        symbol_id=sym.id,
                        section_id=section.id,
                        via="symbol-match",
                        score=1.0,
                    )
                )
    return links
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_linker.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/index/linker.py tests/unit/test_linker.py
git commit -m "feat: deterministic symbol-to-section linking by name"
```

---

## Task 8: Index store (JSON round-trip)

**Files:**
- Modify: `src/index/store.py`
- Test: `tests/unit/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_store.py
from src.models import Symbol, DocSection, Link, Index
from src.index.store import save_index, load_index


def _sample_index():
    sym = Symbol(
        id="app.py::create_user", name="create_user", qualified_name="create_user",
        kind="function", signature="def create_user():", docstring="Make a user.",
        file="app.py", start_line=1, end_line=2, language="python",
    )
    sec = DocSection(
        id="README.md#users", heading_path=("Users",), file="README.md", raw="...",
        start_line=1, end_line=5, referenced_symbols=("create_user",),
        referenced_config_keys=(),
    )
    link = Link(symbol_id=sym.id, section_id=sec.id, via="symbol-match", score=1.0)
    return Index(symbols={sym.id: sym}, sections={sec.id: sec}, links=[link])


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "index.json"
    original = _sample_index()
    save_index(original, str(path))
    loaded = load_index(str(path))

    assert loaded.symbols["app.py::create_user"].name == "create_user"
    assert loaded.sections["README.md#users"].heading_path == ("Users",)
    assert loaded.sections["README.md#users"].referenced_symbols == ("create_user",)
    assert loaded.links[0].via == "symbol-match"
    assert loaded.links[0].score == 1.0


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / ".docsmith" / "index.json"
    save_index(_sample_index(), str(path))
    assert path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_store.py -v`
Expected: FAIL with `ImportError: cannot import name 'save_index'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/index/store.py
"""Persist and load the index as JSON (default: .docsmith/index.json)."""

from __future__ import annotations

import json
import os

from src.models import DocSection, Index, Link, Symbol


def save_index(index: Index, path: str) -> None:
    """Serialize an Index to JSON, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "symbols": {sid: vars(s) for sid, s in index.symbols.items()},
        "sections": {cid: _section_to_dict(c) for cid, c in index.sections.items()},
        "links": [vars(link) for link in index.links],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_index(path: str) -> Index:
    """Load an Index previously written by save_index."""
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    symbols = {sid: Symbol(**data) for sid, data in payload["symbols"].items()}
    sections = {
        cid: _section_from_dict(data) for cid, data in payload["sections"].items()
    }
    links = [Link(**data) for data in payload["links"]]
    return Index(symbols=symbols, sections=sections, links=links)


def _section_to_dict(section: DocSection) -> dict:
    data = vars(section).copy()
    # tuples -> lists for JSON; restored on load
    data["heading_path"] = list(section.heading_path)
    data["referenced_symbols"] = list(section.referenced_symbols)
    data["referenced_config_keys"] = list(section.referenced_config_keys)
    return data


def _section_from_dict(data: dict) -> DocSection:
    return DocSection(
        id=data["id"],
        heading_path=tuple(data["heading_path"]),
        file=data["file"],
        raw=data["raw"],
        start_line=data["start_line"],
        end_line=data["end_line"],
        referenced_symbols=tuple(data["referenced_symbols"]),
        referenced_config_keys=tuple(data["referenced_config_keys"]),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/index/store.py tests/unit/test_store.py
git commit -m "feat: JSON serialization for the index"
```

---

## Task 9: Index builder (walk repo → parse → link)

**Files:**
- Modify: `src/index/builder.py`
- Test: `tests/integration/test_build_index.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_build_index.py
from src.index.builder import build_index
from src.parsing.languages import language_for_path


def test_build_index_over_fixture_repo():
    index = build_index("tests/fixtures/sample_repo")

    # code symbols from app.py and service.ts
    names = {s.name for s in index.symbols.values()}
    assert {"create_user", "UserService", "deactivate", "formatName", "Cache"} <= names

    # doc sections from README.md
    headings = {s.heading_path for s in index.sections.values()}
    assert ("Users",) in headings

    # deterministic links: Users section -> create_user / UserService / deactivate
    linked_symbol_names = {
        index.symbols[link.symbol_id].name
        for link in index.links
        if index.sections[link.section_id].heading_path == ("Users",)
    }
    assert {"create_user", "UserService", "deactivate"} <= linked_symbol_names


def test_build_index_skips_unsupported_files():
    index = build_index("tests/fixtures/sample_repo")
    for sym in index.symbols.values():
        assert language_for_path(sym.file) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_build_index.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_index'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/index/builder.py
"""Build the code↔docs index by walking a repository (full scan).

Incremental updates for changed files are added in the Retrieval-layer plan.
"""

from __future__ import annotations

import os

from src.index.linker import link_by_name
from src.index.store import save_index
from src.models import Index
from src.parsing.code_parser import parse_file
from src.parsing.doc_parser import parse_markdown
from src.parsing.languages import language_for_path

_SKIP_DIRS = {".git", ".docsmith", "node_modules", ".venv", "venv", "__pycache__"}


def build_index(repo_root: str, output_path: str | None = None) -> Index:
    """Parse every supported source and markdown file under repo_root and link them.

    Args:
        repo_root: Directory to scan.
        output_path: If given, persist the index here (e.g. ".docsmith/index.json").
    Returns:
        The built Index.
    """
    symbols = {}
    sections = {}

    for path in _walk(repo_root):
        if language_for_path(path) is not None:
            for sym in parse_file(path):
                symbols[sym.id] = sym
        elif path.lower().endswith(".md"):
            for section in parse_markdown(path):
                sections[section.id] = section

    links = link_by_name(symbols, sections)
    index = Index(symbols=symbols, sections=sections, links=links)

    if output_path is not None:
        save_index(index, output_path)
    return index


def _walk(repo_root: str):
    """Yield file paths under repo_root, skipping noise directories."""
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            yield os.path.join(dirpath, name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_build_index.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/index/builder.py tests/integration/test_build_index.py
git commit -m "feat: build full code-docs index from a repository"
```

---

## Task 10: `build-index` CLI subcommand

**Files:**
- Modify: `docsmith.py`
- Test: `tests/integration/test_cli_build_index.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cli_build_index.py
import json
import subprocess
import sys


def test_cli_builds_index_to_output(tmp_path):
    out = tmp_path / "index.json"
    result = subprocess.run(
        [
            sys.executable, "docsmith.py", "build-index",
            "--repo", "tests/fixtures/sample_repo",
            "--output", str(out),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    data = json.loads(out.read_text())
    assert any(s["name"] == "create_user" for s in data["symbols"].values())
    assert "symbols" in data and "sections" in data and "links" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_cli_build_index.py -v`
Expected: FAIL — `docsmith.py` currently raises `NotImplementedError`.

- [ ] **Step 3: Write minimal implementation**

```python
# docsmith.py
"""Docsmith entry point.

Usable locally and (later) inside the GitHub Action. For now it exposes index building:

    python docsmith.py build-index --repo . --output .docsmith/index.json
"""

from __future__ import annotations

import argparse

from src.index.builder import build_index


def main() -> None:
    parser = argparse.ArgumentParser(prog="docsmith")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-index", help="Build the code↔docs index for a repo.")
    build.add_argument("--repo", default=".", help="Repository root to scan.")
    build.add_argument(
        "--output", default=".docsmith/index.json", help="Where to write the index JSON."
    )

    args = parser.parse_args()

    if args.command == "build-index":
        index = build_index(args.repo, output_path=args.output)
        print(
            f"Indexed {len(index.symbols)} symbols, {len(index.sections)} sections, "
            f"{len(index.links)} links -> {args.output}"
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_cli_build_index.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite and lint**

Run: `pytest && ruff check .`
Expected: all tests pass; ruff reports no errors.

- [ ] **Step 6: Commit**

```bash
git add docsmith.py tests/integration/test_cli_build_index.py
git commit -m "feat: add build-index CLI subcommand"
```

---

## Definition of Done

- `python docsmith.py build-index --repo <path>` writes a valid `.docsmith/index.json`.
- Symbols extracted for Python (with docstrings), TypeScript, JavaScript, and Go.
- Markdown parsed into heading sections with symbol/config-key references.
- Sections deterministically linked to symbols by name.
- Index round-trips through JSON.
- Full `pytest` suite green; `ruff check .` clean.
- No LLM calls anywhere in this subsystem.
