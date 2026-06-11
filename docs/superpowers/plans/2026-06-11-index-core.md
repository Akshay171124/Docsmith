# Index Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Plan style:** This document is a *plan*, not the source. It specifies interfaces, behavior, and the tests to write — the implementer writes the actual code into `src/`/`tests/` during execution (TDD: failing test → implement → green → commit).

**Goal:** Build the persisted, queryable code↔docs index — parse a repository into code symbols (tree-sitter, multi-language) and documentation sections (markdown + docstrings), link them deterministically by name, and serialize the result to `.docsmith/index.json`.

**Architecture:** Pure, deterministic, zero-LLM. A `parsing` layer turns source files into `Symbol`s and doc files into `DocSection`s. A `builder` walks a repo, runs both parsers, and links sections to symbols by name match. A `store` serializes the `Index` to JSON and reads it back. Everything is a pure function over inputs, so the whole subsystem is unit-testable with fixtures. Embeddings and incremental updates are deferred to the Week 2 "Retrieval layer" plan.

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

## Data Contracts

These shapes are fixed up front because every later task and the JSON format depend on them. Field names and types are the contract; the implementer writes the dataclasses in Task 1.

- **`Symbol`** (frozen): `id` (`"path::Qualified.name"`), `name`, `qualified_name`, `kind` (`function|class|method`), `signature`, `docstring` (`str|None`), `file`, `start_line`, `end_line`, `language`.
- **`DocSection`** (frozen): `id` (`"file#heading-slug"`), `heading_path` (tuple of str), `file`, `raw`, `start_line`, `end_line`, `referenced_symbols` (tuple), `referenced_config_keys` (tuple).
- **`Link`** (frozen): `symbol_id`, `section_id`, `via` (`symbol-match|embedding|both`), `score` (float).
- **`Index`**: `symbols` (dict `id→Symbol`), `sections` (dict `id→DocSection`), `links` (list of `Link`).

---

## Task 0: Pin dependencies and create the fixture repo

**Files:**
- Modify: `requirements.txt`
- Create: `tests/fixtures/sample_repo/{app.py, service.ts, README.md}`

**What to do:**
- `tree-sitter-languages` 1.10.x requires `tree-sitter` 0.21.x — replace the loose parsing pins in `requirements.txt` with exact pins: `tree-sitter==0.21.3`, `tree-sitter-languages==1.10.2`.
- Build a tiny fixture repo with known, hand-verifiable contents:
  - `app.py` — a top-level function `create_user(name, email)` with a multi-line docstring, and a class `UserService` with a method `deactivate(user_id)` that has a docstring.
  - `service.ts` — an exported function `formatName(first, last)` and an exported class `Cache` with a `get` method.
  - `README.md` — headings `# Sample App`, `## Users` (references `create_user`, `UserService`, `deactivate` in inline code), `## Formatting` (references `formatName`), `## Config` (references the env var `MAX_USERS`).

**Steps:**
- [ ] Pin the two tree-sitter lines in `requirements.txt`.
- [ ] Run `pip install -r requirements.txt`. Verify: `python -c "from tree_sitter_languages import get_parser; get_parser('python')"` exits 0.
- [ ] Create the three fixture files with the contents described above.
- [ ] Commit: `test: pin tree-sitter and add sample fixture repo`.

---

## Task 1: Core data models

**Files:** Create `src/models.py`; test `tests/unit/test_models.py`.

**Interface:** The four dataclasses from **Data Contracts**. `Symbol`, `DocSection`, `Link` are `@dataclass(frozen=True)` (hashable); `Index` is a mutable dataclass with `default_factory` collections.

**Tests to write (failing first):**
- A constructed `Symbol` exposes its fields and is hashable (`{sym}` works).
- An empty `Index()` has empty `symbols`, `sections`, `links`.

**Steps:**
- [ ] Write the failing tests above.
- [ ] Run them — expect `ModuleNotFoundError: src.models`.
- [ ] Implement `src/models.py` per the Data Contracts.
- [ ] Run — expect green.
- [ ] Commit: `feat: add core index data models`.

---

## Task 2: Language registry

**Files:** Modify `src/parsing/languages.py`; test `tests/unit/test_languages.py`.

**Interface:**
- `language_for_path(path: str) -> str | None` — map by file extension.
- `SUPPORTED_LANGUAGES: list[str]` and `SYMBOL_QUERIES: dict[str, str]`.

**Behavior:**
- Extensions → languages: `.py`→python, `.ts`/`.tsx`→typescript, `.js`/`.jsx`→javascript, `.go`→go. Unknown → `None`.
- `SYMBOL_QUERIES` holds one tree-sitter S-expression query per language, each capturing a definition node as `@def` and its name node as `@name`. Cover: functions, classes, and methods per language (TS class names are `type_identifier`; Go types use `type_declaration`/`type_spec`, methods use `field_identifier`). Capture names MUST be exactly `@def` and `@name` — the parser depends on them.

**Tests to write (failing first):**
- `language_for_path` maps each known extension correctly and returns `None` for `.txt`/`Makefile`.
- Every language in `SUPPORTED_LANGUAGES` has a non-empty entry in `SYMBOL_QUERIES`.

**Steps:**
- [ ] Write the failing tests.
- [ ] Run — expect import error.
- [ ] Implement the extension map and queries.
- [ ] Run — expect green.
- [ ] Commit: `feat: add language registry and symbol queries`.

---

## Task 3: Code parser — Python symbols with docstrings

**Files:** Modify `src/parsing/code_parser.py`; test `tests/unit/test_code_parser.py`.

**Interface:** `parse_file(path: str) -> list[Symbol]` — returns `[]` for unsupported languages.

**Behavior / algorithm:**
1. Resolve language via `language_for_path`; bail early if `None`.
2. Read bytes; get parser/language from `tree_sitter_languages`; run the language's `SYMBOL_QUERIES` query over the tree.
3. Collect captured `@def` nodes and `@name` nodes separately. Pair each name with the **smallest `@def` node whose byte range contains it** — this is robust to nesting (a method name is inside both its class and method nodes; the method node wins). Avoid re-running the query per node.
4. For each (def, name) pair build a `Symbol`:
   - `qualified_name`: prefix with the enclosing class name if the def sits inside a `class_definition`/`class_declaration`, else the bare name.
   - `kind`: `class` for class/type defs; `method` if the node is a method type or the qualified name contains a `.`; else `function`.
   - `signature`: the first line of the def's source text.
   - `docstring`: Python-only best-effort — the string literal that is the first statement of the def body; strip quotes/whitespace. `None` for other languages.
   - line numbers are 1-based.

**Tests to write (failing first), against `tests/fixtures/sample_repo/app.py`:**
- Extracts names `{create_user, UserService, deactivate}`.
- `create_user`: `kind == "function"`, signature starts with `def create_user(`, docstring contains "Create a user record", `language == "python"`.
- `deactivate` has `qualified_name == "UserService.deactivate"` and `kind == "method"`.

**Steps:**
- [ ] Write the failing tests.
- [ ] Run — expect import error.
- [ ] Implement `parse_file` and its helpers per the algorithm.
- [ ] Run — expect green.
- [ ] Commit: `feat: extract Python symbols with docstrings via tree-sitter`.

---

## Task 4: Code parser — TypeScript, JavaScript, Go

**Files:** Test `tests/unit/test_code_parser_multilang.py`. (No source change expected — the parser is language-driven; this task proves it and fixes any per-grammar capture-name mismatch in `languages.py`.)

**Tests to write (failing first):**
- `service.ts`: extracts `formatName` (`language == "typescript"`) and class `Cache` (`kind == "class"`).
- `parse_file` on `README.md` (unsupported) returns `[]`.

**Steps:**
- [ ] Write the failing tests.
- [ ] Run. If a query raised `QueryError`, adjust that language's entry in `SYMBOL_QUERIES` to match the grammar's node names; make the minimal change.
- [ ] Run — expect green.
- [ ] Commit: `test: verify multi-language symbol extraction`.

---

## Task 5: Doc parser — split into sections

**Files:** Modify `src/parsing/doc_parser.py`; test `tests/unit/test_doc_parser_sections.py`.

**Interface:** `parse_markdown(path: str) -> list[DocSection]`.

**Behavior:**
- Split the file into one section per heading line (`#`–`######`). A section spans from its heading line to the line before the next heading (or EOF). Content before the first heading is ignored.
- `heading_path` is a tuple of the heading text (single-element for now; nesting handled in a later plan). `id` is `f"{path}#{slug(heading)}"` where slug lowercases and replaces non-alphanumerics with `-`.
- Capture `raw` body text and 1-based `start_line`/`end_line`.
- Populate `referenced_symbols`/`referenced_config_keys` via the extractor in Task 6 (stub it minimally here or implement together — tests for extraction live in Task 6).

**Tests to write (failing first), against the fixture `README.md`:**
- Sections include heading paths `("Sample App",)`, `("Users",)`, `("Formatting",)`, `("Config",)`.
- The `Users` section's `raw` contains `create_user`, `start_line < end_line`, `file` ends with `README.md`, and `id == "tests/fixtures/sample_repo/README.md#users"`.

**Steps:**
- [ ] Write the failing tests.
- [ ] Run — expect import error.
- [ ] Implement `parse_markdown`.
- [ ] Run — expect green.
- [ ] Commit: `feat: parse markdown into heading-delimited sections`.

---

## Task 6: Doc parser — reference extraction

**Files:** Modify `src/parsing/doc_parser.py` (reference extractor); test `tests/unit/test_doc_parser_refs.py`.

**Interface:** internal helper, e.g. `_extract_references(text) -> (symbols: tuple, config_keys: tuple)`, called by `parse_markdown`.

**Behavior:**
- Scan inline-code spans (text between backticks). For each token: if it matches an ALL-CAPS config-key pattern (e.g. `MAX_USERS`, `^[A-Z][A-Z0-9_]{2,}$`) classify as a config key; else if it's a valid identifier classify as a symbol. Check the config-key branch **before** the identifier branch. De-duplicate while preserving order.

**Tests to write (failing first):**
- `Users` section: `referenced_symbols` includes `create_user`, `UserService`, `deactivate`.
- `Config` section: `MAX_USERS` is in `referenced_config_keys` and NOT in `referenced_symbols`.

**Steps:**
- [ ] Write the failing tests.
- [ ] Run — expect failure if extractor not yet implemented.
- [ ] Implement `_extract_references` and wire it into `parse_markdown`.
- [ ] Run — expect green.
- [ ] Commit: `feat: extract symbol and config-key references from doc sections`.

---

## Task 7: Deterministic linker

**Files:** Create `src/index/linker.py`; test `tests/unit/test_linker.py`.

**Interface:** `link_by_name(symbols: dict[str, Symbol], sections: dict[str, DocSection]) -> list[Link]`.

**Behavior:**
- Build a `name → [Symbol]` map. For each section, for each `referenced_symbol`, emit a `Link(symbol_id, section_id, via="symbol-match", score=1.0)` for every symbol sharing that bare name (so a method matches on its bare name even when its `qualified_name` is class-prefixed). No link when no name matches.

**Tests to write (failing first):**
- Section referencing `create_user` → exactly one link to the matching symbol with `via == "symbol-match"`, `score == 1.0`.
- Section referencing an unknown name → `[]`.
- A method symbol (`qualified_name == "UserService.deactivate"`) is linked when a section references the bare name `deactivate`.

**Steps:**
- [ ] Write the failing tests (with small in-test `Symbol`/`DocSection` builders).
- [ ] Run — expect module-not-found.
- [ ] Implement `link_by_name`.
- [ ] Run — expect green.
- [ ] Commit: `feat: deterministic symbol-to-section linking by name`.

---

## Task 8: Index store (JSON round-trip)

**Files:** Modify `src/index/store.py`; test `tests/unit/test_store.py`.

**Interface:** `save_index(index: Index, path: str) -> None` and `load_index(path: str) -> Index`.

**Behavior:**
- `save_index` creates parent dirs as needed and writes JSON with `symbols`/`sections`/`links` keys. Tuples (`heading_path`, `referenced_*`) serialize as JSON arrays and must restore to tuples on load so frozen dataclasses stay hashable and equal.
- `load_index` reconstructs the exact dataclasses.

**Tests to write (failing first):**
- Build a small `Index`, `save_index` then `load_index` — symbol name, section `heading_path` (as tuple), `referenced_symbols` (as tuple), and link `via`/`score` all survive.
- `save_index` to a nested path (e.g. `tmp/.docsmith/index.json`) creates the directories.

**Steps:**
- [ ] Write the failing tests (use pytest `tmp_path`).
- [ ] Run — expect import error.
- [ ] Implement `save_index`/`load_index` with tuple↔list handling.
- [ ] Run — expect green.
- [ ] Commit: `feat: JSON serialization for the index`.

---

## Task 9: Index builder (walk repo → parse → link)

**Files:** Modify `src/index/builder.py`; test `tests/integration/test_build_index.py`.

**Interface:** `build_index(repo_root: str, output_path: str | None = None) -> Index`.

**Behavior:**
- Walk `repo_root`, skipping noise dirs (`.git`, `.docsmith`, `node_modules`, `.venv`, `venv`, `__pycache__`).
- For each file: if `language_for_path` is not `None`, run `parse_file` and collect symbols by id; else if it ends in `.md`, run `parse_markdown` and collect sections by id.
- Link with `link_by_name`; assemble `Index`. If `output_path` given, `save_index` to it.

**Tests to write (failing first), against `tests/fixtures/sample_repo`:**
- Symbol names superset includes `{create_user, UserService, deactivate, formatName, Cache}`.
- Section heading paths include `("Users",)`.
- For links whose section is `("Users",)`, the linked symbol names superset includes `{create_user, UserService, deactivate}`.
- Every indexed symbol's `file` is a supported language (no stray files indexed).

**Steps:**
- [ ] Write the failing tests.
- [ ] Run — expect import error.
- [ ] Implement `build_index` and `_walk`.
- [ ] Run the new tests, then the full `pytest` suite — expect all green.
- [ ] Commit: `feat: build full code-docs index from a repository`.

---

## Task 10: `build-index` CLI subcommand

**Files:** Modify `docsmith.py`; test `tests/integration/test_cli_build_index.py`.

**Interface:** `python docsmith.py build-index --repo <path> --output <file>` (default output `.docsmith/index.json`). Use `argparse` with a `build-index` subcommand; print a one-line summary of counts.

**Tests to write (failing first):**
- Run the CLI via `subprocess` against the fixture repo with a `tmp_path` output; assert exit code 0, the output file exists, the JSON has `symbols`/`sections`/`links`, and some symbol is named `create_user`.

**Steps:**
- [ ] Write the failing test.
- [ ] Run — expect failure (`docsmith.py` currently raises `NotImplementedError`).
- [ ] Implement the `argparse` CLI dispatching to `build_index`.
- [ ] Run the test; then full `pytest && ruff check .` — expect green and clean.
- [ ] Commit: `feat: add build-index CLI subcommand`.

---

## Definition of Done

- `python docsmith.py build-index --repo <path>` writes a valid `.docsmith/index.json`.
- Symbols extracted for Python (with docstrings), TypeScript, JavaScript, and Go.
- Markdown parsed into heading sections with symbol/config-key references.
- Sections deterministically linked to symbols by name.
- Index round-trips through JSON.
- Full `pytest` suite green; `ruff check .` clean.
- No LLM calls anywhere in this subsystem.
