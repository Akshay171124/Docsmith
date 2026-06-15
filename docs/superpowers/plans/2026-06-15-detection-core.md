# Detection Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Plan style:** This is a *plan*, not the source. It specifies interfaces, behavior, and the tests to write — the implementer writes the actual code into `src/`/`tests/` during execution (TDD: failing test → implement → green → commit).

**Goal:** From a PR diff, deterministically produce a list of suspect documentation sections (those a code change may have made stale) by mapping changed lines to code symbols and linking them against the persisted index — no LLM.

**Architecture:** A git adapter parses a unified diff and supplies old/new file contents as `FileChange`s. A symbol mapper parses both sides (tree-sitter, via a new content-based `parse_source`) and classifies each changed symbol. A triage filter drops noise. A candidate linker queries the index (links + name references) for suspect doc sections. A `detect` CLI ties it together. Everything is pure/offline except the git adapter (subprocess) — swapped for PyGithub in Week 5 behind the same `list[FileChange]` contract.

**Tech Stack:** Python 3.11, `unidiff` (diff parsing), `git` CLI (subprocess), existing tree-sitter parsing + index, `pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/utils/config.py` (modify stub) | `load_settings(path, overrides) -> Settings`; minimal `configs/base.yaml` loader. |
| `src/detection/models.py` (create) | `ChangeKind`, `FileChange`, `ChangedSymbol`, `Suspect`, `DetectionResult`. |
| `src/parsing/code_parser.py` (modify) | Extract `parse_source(source, rel_path, language)`; `parse_file` delegates to it. |
| `src/detection/diff_parser.py` (modify stub) | `parse_unified_diff(text) -> dict[path, frozenset[int]]` (via `unidiff`). |
| `src/detection/git_adapter.py` (create) | `collect_changes(repo_root, base, head) -> list[FileChange]` (git subprocess). |
| `src/detection/symbol_mapper.py` (modify stub) | `map_changes(file_changes) -> list[ChangedSymbol]` (parse old+new, classify). |
| `src/detection/triage_filter.py` (modify stub) | `triage(changed_symbols, file_changes, settings) -> (kept, dropped)`. |
| `src/detection/candidate_linker.py` (modify stub) | `find_suspects(changed_symbols, index) -> list[Suspect]`. |
| `src/detection/detector.py` (create) | `detect(repo_root, base, head, index_path, settings) -> DetectionResult`. |
| `docsmith.py` (modify) | `detect` subcommand. |
| `tests/unit/`, `tests/integration/` (add) | One module per unit; git-adapter + detector are integration (temp git repo). |

---

## Data Contracts (fixed up front)

- **`ChangeKind`** (`enum.Enum`): `ADDED`, `REMOVED`, `SIGNATURE_CHANGED`, `BODY_CHANGED`.
- **`FileChange`** (frozen): `path: str` (repo-relative), `old_content: str | None`, `new_content: str | None`, `changed_lines: frozenset[int]` (new-file line numbers added/modified; empty for pure deletion).
- **`ChangedSymbol`** (frozen): `id: str` (`f"{file}::{qualified_name}"`), `name: str`, `qualified_name: str`, `file: str`, `kind: ChangeKind`, `start_line: int`, `end_line: int` (new-side span; old-side for `REMOVED`), `old_signature: str | None`, `new_signature: str | None`.
- **`Suspect`** (frozen): `symbol_id: str`, `section_id: str`, `change_kind: ChangeKind`, `via: str` (`"index-link"` | `"name-reference"`).
- **`DetectionResult`**: `changed_symbols: list[ChangedSymbol]` (post-triage), `suspects: list[Suspect]`, `dropped: dict[str, int]` (reason → count).
- **`Settings`** (config; `src/utils/config.py`): `ignore_paths: list[str]`, `doc_ignore: list[str]`, `skip_comment_only: bool`, `skip_whitespace_only: bool`. `load_settings(path="configs/base.yaml", overrides: dict | None = None) -> Settings`; missing keys → documented defaults (`ignore_paths`/`doc_ignore` → `[]`, the skip flags → `True`).
- **`parse_source(source: str | bytes, rel_path: str, language: str) -> list[Symbol]`** — core tree-sitter parse over in-memory content; `parse_file(path, rel_path=None)` resolves language, reads bytes, and delegates (returns `[]` for unsupported language exactly as today).
- **`collect_changes(repo_root, base, head) -> list[FileChange]`**, **`map_changes(file_changes) -> list[ChangedSymbol]`**, **`triage(changed_symbols, file_changes, settings) -> tuple[list[ChangedSymbol], dict[str,int]]`**, **`find_suspects(changed_symbols, index) -> list[Suspect]`**, **`detect(repo_root, base, head, index_path, settings) -> DetectionResult`** (signatures locked here).

---

## Task 0: Minimal config loader

**Files:** Modify `src/utils/config.py`; test `tests/unit/test_config.py`.

**Interface:** `Settings` dataclass + `load_settings(path="configs/base.yaml", overrides=None) -> Settings` (see Data Contracts).

**Behavior:** Parse the YAML with `PyYAML`; pull `triage.ignore_paths`, `docs.ignore`, `triage.skip_comment_only`, `triage.skip_whitespace_only` into `Settings`. Missing keys → defaults (`[]` for the lists, `True` for the skip flags). `overrides` (a flat dict) shallow-overrides matching `Settings` fields. `from __future__ import annotations`.

**Tests to write (failing first):**
- `load_settings()` on the real `configs/base.yaml` returns `ignore_paths` including `**/test_*.py`, `skip_comment_only is True`, `skip_whitespace_only is True`, and `doc_ignore` including `**/CHANGELOG.md`.
- `load_settings(path=<tmp yaml lacking triage/docs keys>)` returns the documented defaults without raising.
- `overrides={"skip_comment_only": False}` is reflected in the result.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → `ruff check` both files → commit (`feat: add minimal config loader for base.yaml`).

---

## Task 1: Detection data models

**Files:** Create `src/detection/models.py`; test `tests/unit/test_detection_models.py`.

**Interface:** the five types in Data Contracts. `ChangeKind` is an `Enum`; `FileChange`/`ChangedSymbol`/`Suspect` are `@dataclass(frozen=True)`; `DetectionResult` is a mutable `@dataclass` with `default_factory` collections. `from __future__ import annotations`. Pure data, no logic.

**Tests to write (failing first):**
- Construct a `ChangedSymbol` with `kind=ChangeKind.SIGNATURE_CHANGED`; assert field access and that it is hashable (set membership).
- Construct a `FileChange` with `changed_lines=frozenset({3,4})`; assert `old_content`/`new_content` may be `None`.
- `DetectionResult()` defaults: `changed_symbols == []`, `suspects == []`, `dropped == {}`.

**Steps:** failing tests → run (fail, ModuleNotFound) → implement → run (pass) → full suite green → ruff → commit (`feat: add detection data models`).

---

## Task 2: Content-based `parse_source`

**Files:** Modify `src/parsing/code_parser.py`; test `tests/unit/test_parse_source.py` (and the existing `test_code_parser.py` must stay green).

**Interface:** `parse_source(source: str | bytes, rel_path: str, language: str) -> list[Symbol]`. `parse_file(path, rel_path=None)` keeps its signature/behavior but is refactored to: resolve language via `language_for_path(path)` (return `[]` if `None`), read the file bytes, and `return parse_source(bytes, rel_path or path, language)`.

**Behavior:** `parse_source` holds the current tree-sitter logic (normalize `str`→`bytes`; run the language query; build `Symbol`s using `rel_path` for `id`/`file`). It assumes `language` is a supported tree-sitter name (the caller resolved it). No disk access in `parse_source`.

**Tests to write (failing first):**
- `parse_source("def foo():\n    pass\n", "x.py", "python")` returns a `Symbol` named `foo` with `id == "x.py::foo"`, `language == "python"`. (Accepts `str`.)
- `parse_source(b"def foo(): pass\n", "x.py", "python")` works on `bytes` too.
- Regression: the existing `tests/unit/test_code_parser.py` and `test_code_parser_multilang.py` still pass unchanged (parse_file behavior preserved, including `[]` for unsupported and `rel_path` handling).

**Steps:** failing tests → run (fail) → refactor `parse_file` + add `parse_source` → run new + existing parser tests (all pass) → full suite green → ruff → commit (`refactor: extract content-based parse_source from parse_file`).

---

## Task 3: DiffParser

**Files:** Modify `src/detection/diff_parser.py`; test `tests/unit/test_diff_parser.py`.

**Interface:** `parse_unified_diff(diff_text: str) -> dict[str, frozenset[int]]`.

**Behavior:** Use `unidiff.PatchSet(diff_text)`. For each patched file, key by the **target** (new) path; value = frozenset of **target/new line numbers** for added lines (`line.is_added` with `line.target_line_no`). A removed-only file still appears with an empty set. Skip files with no hunks (binary/mode-only). `from __future__ import annotations`.

**Tests to write (failing first):** craft small unified-diff strings inline:
- A modify hunk (one line added at new-line 4) → `{"a.py": frozenset({4})}`.
- A multi-hunk / multi-line-added diff → all added new-line numbers present.
- A pure-deletion file appears as a key with an empty frozenset.
- An added file → all its new-line numbers present.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: parse unified diffs into changed line numbers`).

---

## Task 4: GitAdapter

**Files:** Create `src/detection/git_adapter.py`; test `tests/integration/test_git_adapter.py`.

**Interface:** `collect_changes(repo_root: str, base: str, head: str) -> list[FileChange]`.

**Behavior:**
- `git -C repo diff --name-status base head` → list of `(status, path)` (A/M/D/R…); treat `R` (rename) as a delete of the old path + add of the new path.
- `git -C repo diff --unified base head` → diff text → `parse_unified_diff` → `{path: changed_lines}`.
- Restrict to files Docsmith indexes: `language_for_path(path) is not None or path.lower().endswith(".md")`. Ignore others.
- For each kept file build a `FileChange`:
  - `old_content` = `git -C repo show base:path` decoded, or `None` if status is added.
  - `new_content` = `git -C repo show head:path` decoded, or `None` if status is deleted.
  - `changed_lines` from the diff map (or `frozenset()` for deletes).
- Never `git show` the absent side. Use `subprocess.run([...], capture_output=True, text=True, check=...)`; handle the show of a path that doesn't exist on a side via the status, not by catching errors.

**Tests to write (failing first) — integration, build a temp git repo with `subprocess`:**
- `git init`, write `app.py` (+ a `README.md`), commit (base). Modify `app.py` (change a function body), add `new.py`, delete `README.md`, commit (head).
- `collect_changes(tmp, base_sha, head_sha)` returns `FileChange`s where: `app.py` has both contents + non-empty `changed_lines`; `new.py` has `old_content is None`; `README.md` has `new_content is None`. Unsupported files (if any) are absent.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: git adapter producing FileChanges from a ref range`).

---

## Task 5: SymbolMapper

**Files:** Modify `src/detection/symbol_mapper.py`; test `tests/unit/test_symbol_mapper.py`.

**Interface:** `map_changes(file_changes: list[FileChange]) -> list[ChangedSymbol]`.

**Behavior:** For each `FileChange` whose path is a supported code language (skip `.md`):
- `language = language_for_path(path)`. `old = {qn: Symbol}` from `parse_source(old_content, path, language)` if `old_content` else `{}`; `new` likewise from `new_content`.
- Classify per `qualified_name`:
  - **ADDED**: in `new` not `old` (and the new symbol's span overlaps `changed_lines` — always true for genuinely new code).
  - **REMOVED**: in `old` not `new`.
  - In both: **SIGNATURE_CHANGED** if `old.signature != new.signature`; else **BODY_CHANGED** if the new symbol's span overlaps `changed_lines`; else omit (unchanged).
- Build `ChangedSymbol`: `id=f"{path}::{qn}"`, `name`=bare name, `start_line`/`end_line` from the new symbol (old symbol for REMOVED), `old_signature`/`new_signature` from the respective `Symbol`s (`None` where absent).
- "Span overlaps changed_lines": any line in `[start_line, end_line]` ∈ `changed_lines`.

**Tests to write (failing first)** — hand-write old/new Python content strings (no git needed); wrap each in a `FileChange(path="m.py", old_content=..., new_content=..., changed_lines=frozenset({...}))`:
- Add a new function → one `ADDED` symbol.
- Remove a function → one `REMOVED` symbol (`new_signature is None`).
- Change a function's signature (e.g. add a param) with that line in `changed_lines` → `SIGNATURE_CHANGED` (both signatures populated, differing).
- Change only a function's body line (signature identical, body line in `changed_lines`) → `BODY_CHANGED`.
- A function untouched (no overlap, same signature) → omitted from results.
- Rename a function → results contain a `REMOVED` (old name) and an `ADDED` (new name).

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: map diff changes to classified code symbols`).

---

## Task 6: TriageFilter

**Files:** Modify `src/detection/triage_filter.py`; test `tests/unit/test_triage_filter.py`.

**Interface:** `triage(changed_symbols: list[ChangedSymbol], file_changes: list[FileChange], settings: Settings) -> tuple[list[ChangedSymbol], dict[str, int]]`.

**Behavior:** Build `path -> FileChange`. For each changed symbol, drop (incrementing the matching `dropped` reason) when:
- `path` matches any glob in `settings.ignore_paths` or `settings.doc_ignore` → reason `"ignored_path"` (use `fnmatch`/`pathlib.PurePath.match`; `**` globs — use a matcher that supports `**`, e.g. `pathlib.PurePath(path).match` per-pattern, or `fnmatch` on the full path).
- `settings.skip_whitespace_only` and `kind == BODY_CHANGED` and every changed line within the symbol's span (`changed_lines ∩ [start_line, end_line]`, read from `new_content`) is blank/whitespace → reason `"whitespace_only"`.
- `settings.skip_comment_only` and `kind == BODY_CHANGED` and every such changed line is blank or starts (after lstrip) with the language's comment marker (`#` python, `//` ts/js/go — a small per-language map) → reason `"comment_only"`. Best-effort (block/inline comments not handled).
- Otherwise keep. Returns `(kept, dropped_counts)`.

**Tests to write (failing first):**
- A symbol in a file matching `**/test_*.py` is dropped (`ignored_path`).
- A `BODY_CHANGED` symbol whose changed lines are all whitespace is dropped (`whitespace_only`); counts reflect it.
- A `BODY_CHANGED` symbol whose changed lines are all `#`-comments (python) is dropped (`comment_only`).
- A real body change (a code line) is kept.
- `skip_comment_only=False` (via a `Settings`) → the comment-only symbol is kept.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: triage filter for ignored/test/comment/whitespace changes`).

---

## Task 7: CandidateLinker

**Files:** Modify `src/detection/candidate_linker.py`; test `tests/unit/test_candidate_linker.py`.

**Interface:** `find_suspects(changed_symbols: list[ChangedSymbol], index: Index) -> list[Suspect]`.

**Behavior:** For each changed symbol:
- **index-link**: for every `Link` in `index.links` with `link.symbol_id == cs.id`, emit `Suspect(cs.id, link.section_id, cs.kind, via="index-link")`.
- **name-reference**: for every `DocSection` in `index.sections.values()` whose `referenced_symbols` contains `cs.name`, emit `Suspect(cs.id, section.id, cs.kind, via="name-reference")`.
- Dedup by `(symbol_id, section_id)`, preferring `via="index-link"` when a pair arises both ways. Deterministic order (index-link suspects first, in input order).

**Tests to write (failing first)** — build a small `Index` directly (hand-construct `Symbol`/`DocSection`/`Link`, or use the Week-1 builder on a tiny fixture):
- A changed symbol whose `id` matches an `index.links` entry → an `index-link` suspect for that section.
- A `REMOVED` changed symbol whose `name` is in a section's `referenced_symbols` but is absent from `index.links` → a `name-reference` suspect (proves the removed-symbol path).
- A pair reachable both ways → a single suspect with `via == "index-link"` (dedup + preference).
- **Path-alignment guard:** build an `Index` via the real builder (`embeddings=False`) over a tiny repo, take a real symbol id from it, construct a `ChangedSymbol` with that same `id`, and assert an `index-link` suspect is produced — proving the `f"{file}::{qn}"` id form matches the index's ids.

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: candidate linker mapping changed symbols to suspect doc sections`).

---

## Task 8: Detector orchestrator

**Files:** Create `src/detection/detector.py`; test `tests/integration/test_detector.py`.

**Interface:** `detect(repo_root: str, base: str, head: str, index_path: str, settings: Settings) -> DetectionResult`.

**Behavior:** `collect_changes` → `map_changes` → `triage` (capture `dropped`) → `load_index(index_path)` → `find_suspects(kept, index)`. After linking, count changed symbols that produced zero suspects into `dropped["no_candidates"]`. Return `DetectionResult(changed_symbols=kept, suspects=suspects, dropped=dropped)`.

**Tests to write (failing first) — integration on a temp git repo:**
- Build a temp repo with `app.py` (a documented function, e.g. `create_user`) and a `README.md` referencing `create_user`; commit (base). Build the index for the repo (`build_index(tmp, output_path=idx, embeddings=False)`). Then modify `create_user`'s signature, commit (head).
- `detect(tmp, base, head, idx, load_settings())` → `DetectionResult` whose `suspects` includes the README section for `create_user` (`change_kind == SIGNATURE_CHANGED`), and `changed_symbols` includes `create_user`.
- A whitespace-only change to an unrelated function is dropped (reflected in `dropped`).

**Steps:** failing tests → run (fail) → implement → run (pass) → full suite green → ruff → commit (`feat: detection orchestrator`).

---

## Task 9: `detect` CLI subcommand

**Files:** Modify `docsmith.py`; test `tests/integration/test_cli_detect.py`.

**Interface:** `docsmith detect --repo . --base <ref> --head <ref> [--index .docsmith/index.json] [--config configs/base.yaml]`.

**Behavior:** Add a `detect` subparser. Load `settings = load_settings(args.config)`, run `detect(...)`, print a summary line `Detected N changed symbols, M suspect sections (K dropped)` followed by suspects grouped by doc file (resolve each `section_id` to its file via `index.sections`). Read-only, exit 0.

**Tests to write (failing first) — integration via `subprocess`, temp git repo + built index:**
- After building an index and making a signature change (as in Task 8), run `docsmith detect --repo <tmp> --base <sha> --head <sha> --index <idx>`; assert exit 0, stdout contains `Detected`, and stdout names the README doc file as a suspect.

**Steps:** failing test → run (fail) → implement → run (pass) → full suite green → `ruff check docsmith.py tests/integration/test_cli_detect.py` → commit (`feat: add detect CLI subcommand`).

---

## Definition of Done

- `docsmith detect --repo . --base X --head Y` prints changed symbols + suspect doc sections from a real git range, reading the persisted index.
- Symbol mapping classifies added/removed/signature/body changes; renames surface as removed + added.
- Triage drops ignored/test/comment-only/whitespace-only changes with counted reasons.
- Candidate linking finds suspects via index links and name references (incl. removed symbols), with verified id-form alignment.
- `parse_source` enables content-based parsing without regressing `parse_file`.
- Minimal config loader reads `configs/base.yaml`.
- Full `pytest` suite green; `ruff check .` clean; no LLM/network calls in this subsystem.
