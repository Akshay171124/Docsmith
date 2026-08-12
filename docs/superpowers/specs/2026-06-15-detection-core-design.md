# Detection Core (Week 3) — Design Spec

**Date:** 2026-06-15
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** Index Core (Week 1) + Retrieval Core (Week 2)

---

## 1. Goal & Scope

Turn a pull-request diff into a list of **suspect documentation sections** — sections that
*might* have been made stale by the code change — ready to hand to the LLM staleness
investigator (a separate, later sub-project). This whole sub-project is **deterministic
and zero-LLM**; it is the cheap, explainable front half of the detection pipeline.

**In scope:**
- Diff parsing (unified diff → changed line ranges).
- A git adapter that supplies the diff and both old/new file contents.
- Symbol mapping: map changed lines to code symbols and classify the change kind.
- Triage filtering: drop changes that cannot affect docs.
- Candidate linking: query the persisted index for doc sections tied to changed symbols.
- A `detect` CLI command.
- A minimal config loader (`src/utils/config.py`) reading `configs/base.yaml`, first
  consumed here (clears the Week-2 "config not wired" follow-up).

**Out of scope (own later sub-projects):**
- The LLM staleness investigator (stage 5) and its Claude client seam + tool-use loop.
- Repair, validation, confidence routing (Week 4).
- The GitHub Action / PR reporting (Week 5).

**Non-goals:** No LLM/network calls. No mutation of repos or docs. Detection only reports
suspects; it does not judge or fix them.

---

## 2. Data Flow

```
(repo, base, head)
   │
   ▼  GitAdapter.collect_changes  (git diff base..head; git show base:f / head:f)
[FileChange(path, old_content, new_content, changed_lines)]      ← DiffParser yields changed_lines
   │
   ▼  SymbolMapper.map_changes  (tree-sitter parse old + new; classify)
[ChangedSymbol(name, qualified_name, file, kind, old_signature?, new_signature?)]
   │
   ▼  TriageFilter  (drop ignored/test paths, comment-only / whitespace-only)
[ChangedSymbol]  (surviving)
   │
   ▼  CandidateLinker.find_suspects(changed_symbols, index)
[Suspect(changed_symbol, doc_section, evidence)]
   │
   ▼
DetectionResult(changed_symbols, suspects, dropped)
```

---

## 3. Data Models (`src/detection/models.py`)

- **`ChangeKind`** — `Enum`: `ADDED`, `REMOVED`, `SIGNATURE_CHANGED`, `BODY_CHANGED`.
- **`FileChange`** (frozen): `path: str` (repo-relative), `old_content: str | None` (None if
  added), `new_content: str | None` (None if deleted), `changed_lines: frozenset[int]`
  (new-file line numbers touched; empty for a pure deletion).
- **`ChangedSymbol`** (frozen): `id: str`, `name: str`, `qualified_name: str`, `file: str`,
  `kind: ChangeKind`, `start_line: int`, `end_line: int` (new-side span; old-side for
  `REMOVED`), `old_signature: str | None`, `new_signature: str | None`. The `SymbolMapper`
  sets `id = f"{file}::{qualified_name}"` so it matches the index's repo-relative
  `Symbol.id` scheme (Week 1/2), enabling direct `index.links` matching. The line span lets
  triage inspect which changed lines fall inside the symbol.
- **`Suspect`** (frozen): `symbol_id: str` (the changed symbol's repo-relative id),
  `section_id: str`, `change_kind: ChangeKind`, `via: str` (`"index-link"` | `"name-reference"`).
- **`DetectionResult`**: `changed_symbols: list[ChangedSymbol]`, `suspects: list[Suspect]`,
  `dropped: dict[str, int]` (counts by reason, e.g. `{"ignored_path": 2, "no_candidates": 1}`).

---

## 4. Components

### 4.1 DiffParser (`src/detection/diff_parser.py`)
- `parse_unified_diff(diff_text: str) -> dict[str, frozenset[int]]` — map each changed
  file (new path) to the set of **new-file** line numbers that were added/modified, using
  the `unidiff` library. Pure function over diff text.

### 4.2 GitAdapter (`src/detection/git_adapter.py`)
- `collect_changes(repo_root: str, base: str, head: str) -> list[FileChange]`.
- Uses `git` via subprocess: `git -C repo diff --unified base head` for the diff;
  `git -C repo show base:path` / `head:path` for old/new contents (handle add/delete where
  one side is absent). Paths are repo-relative. Restricts to files Docsmith indexes
  (supported language or `.md`) — others are ignored here.
- This is the one component that touches the environment; it is swapped for a PyGithub
  adapter in Week 5 behind the same `list[FileChange]` output contract.

### 4.3 SymbolMapper (`src/detection/symbol_mapper.py`)
- `map_changes(file_changes: list[FileChange]) -> list[ChangedSymbol]`.
- **Prerequisite — content-based parsing.** `parse_file(path)` reads from disk, but the
  mapper has in-memory `old_content`/`new_content` strings (from `git show`), not paths.
  So `src/parsing/code_parser.py` is refactored to expose
  `parse_source(source: str | bytes, rel_path: str, language: str) -> list[Symbol]`, and
  `parse_file` becomes a thin wrapper that reads the file, resolves the language, and
  delegates to `parse_source`. This is behavior-preserving for existing `parse_file`
  callers (Week-1/2 tests must stay green).
- For each code `FileChange` (skip `.md` — those are doc changes, handled elsewhere):
  parse `old_content` and `new_content` via `parse_source` (language from
  `language_for_path(path)`, `rel_path = path`), giving old/new symbol sets keyed by
  `qualified_name`.
  - **added**: qn in new not old, and the symbol overlaps `changed_lines`.
  - **removed**: qn in old not new.
  - in both: **signature_changed** if the signature line differs; else **body_changed**
    if the symbol's new span overlaps `changed_lines` (its body actually changed).
    Symbols in both with no overlap and identical signature are unchanged → omitted.
- `old_signature`/`new_signature` populated from the respective parses.

### 4.4 TriageFilter (`src/detection/triage_filter.py`)
- Drops, per settings:
  - files whose path matches `triage.ignore_paths` or `docs.ignore` globs;
  - test files (same `ignore_paths` patterns, e.g. `**/test_*.py`, `**/*.test.ts`);
  - **whitespace-only** changes when `skip_whitespace_only` is set — exact: a
    `body_changed` symbol whose changed new-lines are all blank/whitespace is dropped.
  - **comment-only** changes when `skip_comment_only` is set — **heuristic**: a per-language
    line-prefix check (`#` for Python, `//` for TS/JS/Go) over the changed new-lines; if
    every changed line is blank or a comment line, drop. Comment markers come from a small
    per-language map in the triage module. This is best-effort (it won't catch block
    comments or trailing inline comments); the LLM investigator is the final arbiter later,
    so a missed drop only means an extra suspect, never a wrong verdict.
- Returns the surviving `ChangedSymbol`s plus a `dropped` counter dict. Logs the drops.
- Operates at the symbol level (it receives both the `ChangedSymbol`s and their owning
  `FileChange`s so it can inspect the changed lines).

### 4.5 CandidateLinker (`src/detection/candidate_linker.py`)
- `find_suspects(changed_symbols, index) -> list[Suspect]`.
- For each changed symbol:
  - **index-link**: any `Link` in `index.links` whose `symbol_id` matches the changed
    symbol's id → that link's `section_id` is a suspect (`via="index-link"`).
  - **name-reference**: any `DocSection` whose `referenced_symbols` contains the changed
    symbol's bare `name` → suspect (`via="name-reference"`). This path catches **removed**
    symbols (absent from the head index's links but still named in prose).
  - Dedup by `(symbol_id, section_id)`, preferring `via="index-link"` when both apply.

### 4.6 Detector (`src/detection/detector.py`)
- `detect(repo_root, base, head, index_path, settings) -> DetectionResult`.
- Orchestrates: `collect_changes` → `map_changes` → `triage` → load index
  (`store.load_index`) → `find_suspects`. Drops changed symbols with zero candidates
  (counted in `dropped["no_candidates"]`). Returns the `DetectionResult`.

### 4.7 Config loader (`src/utils/config.py`)
- `load_settings(path="configs/base.yaml", overrides=None) -> Settings`.
- Loads the YAML and exposes the values detection needs: `triage` rules, `docs.ignore`
  globs, and (for completeness) `linking` settings. `Settings` is a simple typed
  structure (dataclass) with sensible defaults if a key is missing. This is the minimal
  loader; richer layering (repo override, Action inputs) lands when Week 5 needs it.

---

## 5. CLI

`docsmith detect --repo . --base <ref> --head <ref> [--index .docsmith/index.json] [--config configs/base.yaml]`:
- Loads settings + the index, runs `detect`, prints a summary:
  `Detected N changed symbols, M suspect sections (K dropped)` followed by suspects grouped
  by doc file. Exit 0. Read-only — no fixes, no PRs.

---

## 6. Testing (all offline, no LLM)

- **diff_parser**: fixture unified-diff strings → expected changed-line sets (add, modify,
  delete, multi-hunk).
- **git_adapter**: integration test building a **temp git repo** (`git init`, commit a base
  version, commit a head version) and asserting `collect_changes` returns correct
  `FileChange`s (contents + changed_lines) for added/modified/deleted files.
- **symbol_mapper**: hand-crafted old/new content pairs → correct `ChangeKind`s — added,
  removed, rename (= removed + added), signature change, body change; unchanged symbols
  omitted.
- **triage_filter**: drops ignored-path, test-file, comment-only, and whitespace-only
  changes; keeps real changes; returns correct `dropped` counts.
- **candidate_linker**: a fixture `Index` (built via Week-1/2 builder with a `FakeEmbedder`
  or hand-constructed) + changed symbols → correct suspects, including the removed-symbol
  name-reference path and dedup/`via` preference.
- **config loader**: loads `configs/base.yaml`; missing-key defaults applied.
- **detector + CLI**: end-to-end on a temp git repo with a pre-built index — asserts the
  expected suspects and the CLI summary/exit code.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `git show` for added/deleted files (one side absent) errors | Detect add/delete from the diff; pass `old_content=None`/`new_content=None` accordingly; never `git show` a missing side. |
| Symbol mapping false "body_changed" from reformatting | Triage's whitespace/comment-only drop; signature comparison is line-based. Good-enough for the deterministic stage; the LLM investigator is the final arbiter later. |
| Index is stale relative to head (built earlier) | Detection treats the index as the link source; `name-reference` matching backstops missing links. Index freshness is a Week-5 (Action) concern. |
| Path-form mismatch between git adapter output and index ids (`app.py` vs `./app.py`) silently breaks index-link matching | Normalize git-adapter paths with the same convention the index builder uses (`os.path.relpath`-style, no `./` prefix); a candidate-linker test asserts an index built on a repo and a `ChangedSymbol` for the same file produce a matching `index-link` suspect. Name-reference matching is the backstop if it still drifts. |
| Rename detection | Modeled as removed + added (git rename detection not relied upon); the name-reference path flags docs mentioning the old name. |
| `unidiff` parsing edge cases (binary, mode-only) | Skip non-text / no-hunk files; only emit `changed_lines` for text hunks. |

---

## 8. Definition of Done

- `docsmith detect --repo . --base X --head Y` prints changed symbols + suspect doc
  sections for a real git range, reading the persisted index.
- Symbol mapping classifies added/removed/signature/body changes across the supported
  languages.
- Triage drops ignored/test/comment-only/whitespace-only changes with counted reasons.
- Candidate linking finds suspects via both index links and name references (incl. removed
  symbols).
- Minimal config loader reads `configs/base.yaml`.
- Full `pytest` suite green; `ruff check .` clean; no LLM/network calls in this subsystem.
