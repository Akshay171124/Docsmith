# Retrieval Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Plan style:** This is a *plan*, not the source. It specifies interfaces, behavior, and the tests to write — the implementer writes the actual code into `src/`/`tests/` during execution (TDD: failing test → implement → green → commit).

**Goal:** Add embedding-based recall to the index (local bge-small + Chroma), merge it with the existing deterministic symbol-match links into hybrid links, make the index incrementally updatable via per-file content hashes, and normalize ids to repo-relative paths.

**Architecture:** Pure/deterministic except for a local, offline embedding model that sits behind an `Embedder` seam (so tests use a fake). A Chroma collection persists symbol and section vectors under `.docsmith/chroma/`. The builder hashes files, re-embeds only changed files, and recomputes hybrid links fully each build/update. No network, no LLM.

**Tech Stack:** Python 3.11, `sentence-transformers` (bge-small), `chromadb` (file-based), existing tree-sitter parsing, `pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `.github/workflows/ci.yml` (modify) | Run the FULL suite (incl. integration); opt into Node 24. |
| `configs/base.yaml` (modify) | Add `linking.top_k`. |
| `src/models.py` (modify) | Add `Index.file_hashes: dict[str, str]`. |
| `src/parsing/code_parser.py` (modify) | Optional `rel_path` param for repo-relative ids. |
| `src/parsing/doc_parser.py` (modify) | Optional `rel_path` param for repo-relative ids. |
| `src/index/store.py` (modify) | Persist/load `file_hashes`; default `{}` when absent. |
| `src/index/hashing.py` (create) | File content hashing + added/changed/deleted classification. |
| `src/index/embeddings.py` (modify) | `Embedder` protocol, `FakeEmbedder`, `BgeSmallEmbedder`, `VectorStore` (Chroma wrapper). |
| `src/index/linker.py` (modify) | `link_by_embedding` + `merge_links` (keep `link_by_name`). |
| `src/index/builder.py` (modify) | Repo-relative ids; embeddings + hybrid linking; `update_index`; `embeddings`/`full` flags. |
| `docsmith.py` (modify) | Incremental-by-default; `--full`, `--no-embeddings` flags. |
| `tests/unit/`, `tests/integration/` (add) | One test module per new/changed unit. |

---

## Data Contracts (fixed up front)

- **`Index.file_hashes`**: `dict[str, str]` — repo-relative path → hex sha256 of file bytes. Default empty.
- **`linking.top_k`**: int, default `5` (new key under `linking:` in `configs/base.yaml`, alongside existing `embedding_similarity_threshold: 0.55`).
- **`Embedder` protocol** (`src/index/embeddings.py`): method `embed_texts(texts: list[str]) -> list[list[float]]`. Implementations: `FakeEmbedder` (deterministic, hash-seeded, fixed small dim e.g. 16, normalized) for tests; `BgeSmallEmbedder` (wraps `sentence-transformers` `BAAI/bge-small-en-v1.5`, normalized embeddings) for real use.
- **`VectorStore`** (`src/index/embeddings.py`): wraps a Chroma collection created with cosine space (`metadata={"hnsw:space": "cosine"}`), owns an `Embedder`. Each stored vector carries metadata `{"group": "symbol"|"section", "file": <repo-relative path>}` and is keyed by the entity id (`Symbol.id` / `DocSection.id`). Methods:
  - `add(group, items)` where `items: list[(id, text, file)]` — embeds texts and upserts.
  - `query(query_text, group, top_k) -> list[(id, similarity)]` — embeds `query_text`, searches within `group`, returns ids + cosine **similarity** (`1 - distance`), filtered to caller's threshold by the caller.
  - `delete_by_files(files: set[str])` — removes all vectors whose `file` metadata is in `files`.
  - `reset()` — drop the collection (for `--full`).
- **Embedding text builders** (in `embeddings.py` or `builder.py`, pick one and keep it there):
  - symbol → `"{kind} {qualified_name}\n{signature}\n{docstring or ''}"` (no trailing blank line when docstring is None).
  - section → `"{heading_path joined by ' > '}\n{raw}"`.
- **`Link.via`** values now in use: `"symbol-match"`, `"embedding"`, `"both"` (already defined on the model).
- **`build_index(repo_root, output_path=None, *, embeddings=True, full=False, embedder=None) -> Index`** and **`update_index(repo_root, output_path, *, embeddings=True, embedder=None) -> Index`** (signatures locked here). `embedder` is the injection seam: `None` → use `BgeSmallEmbedder()`; tests pass a `FakeEmbedder()`. Ignored when `embeddings=False`.

---

## Task 0: Carried-over CI fixes + `top_k` config

**Files:** Modify `.github/workflows/ci.yml`, `configs/base.yaml`.

**What to do:**
- CI: change the test step from `pytest tests/unit` to `pytest` (so integration tests are gated too). Add a top-level `env: { FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true" }` to silence the Node 20 deprecation. (If a real-model test is added later it must self-skip without `DOCSMITH_RUN_MODEL_TESTS=1`, so plain `pytest` stays offline — see Task 4.)
- Config: under `linking:` in `configs/base.yaml`, add `top_k: 5` next to `embedding_similarity_threshold: 0.55`.

**Steps:**
- [ ] Edit `ci.yml` (full-suite test step + Node 24 env).
- [ ] Add `top_k: 5` to `configs/base.yaml`.
- [ ] Locally run `python3 -m pytest -q` (still green) and `ruff check .` (clean).
- [ ] Commit (`ci: run full suite and opt into Node 24; add linking.top_k config`).

---

## Task 1: Repo-relative id normalization

**Files:** Modify `src/parsing/code_parser.py`, `src/parsing/doc_parser.py`; tests `tests/unit/test_code_parser.py`, `tests/unit/test_doc_parser_sections.py` (extend).

**Interface:** add an optional keyword param to both parsers:
- `parse_file(path: str, rel_path: str | None = None) -> list[Symbol]`
- `parse_markdown(path: str, rel_path: str | None = None) -> list[DocSection]`

**Behavior:** the file is still OPENED via `path`, but the `file` field and the `id` prefix use `rel_path` when provided, else `path` (current behavior preserved). So `parse_file("/abs/app.py", rel_path="app.py")` yields `Symbol.id == "app.py::create_user"` and `Symbol.file == "app.py"`; markdown ids become `"app.py.md#..."`-style with the rel path. When `rel_path` is None, all existing Week-1 behavior is unchanged.

**Tests to add (failing first):**
- `parse_file(<fixture app.py abs or given path>, rel_path="app.py")` → the `create_user` symbol has `id == "app.py::create_user"` and `file == "app.py"`.
- `parse_markdown(<fixture README.md>, rel_path="README.md")` → the Users section has `id == "README.md#users"` and `file == "README.md"`.
- Existing no-`rel_path` tests still pass unchanged (regression guard).

**Steps:** add failing tests → run (fail) → implement the optional param threading through id/file construction → run (pass) → full suite green → ruff clean → commit (`feat: support repo-relative ids via rel_path in parsers`).

---

## Task 2: `Index.file_hashes` model field + store round-trip

**Files:** Modify `src/models.py`, `src/index/store.py`; tests `tests/unit/test_models.py`, `tests/unit/test_store.py` (extend).

**Interface/behavior:**
- `Index` gains `file_hashes: dict[str, str]` with `default_factory=dict`.
- `save_index` writes a top-level `"file_hashes"` key (a JSON object). `load_index` reads it, **defaulting to `{}` when the key is absent** (so a Week-1 index without the field still loads).

**Tests to add (failing first):**
- A round-tripped `Index` with a non-empty `file_hashes` (e.g. `{"app.py": "abc123"}`) preserves it exactly.
- `load_index` on a JSON payload that omits `file_hashes` returns an `Index` with `file_hashes == {}` (write a small JSON file without the key in the test).

**Steps:** failing tests → implement model field + store read/write with graceful default → run (pass) → full suite green → ruff clean → commit (`feat: persist per-file content hashes in the index`).

---

## Task 3: File hashing + change classification

**Files:** Create `src/index/hashing.py`; test `tests/unit/test_hashing.py`.

**Interface:**
- `hash_file(path: str) -> str` — hex sha256 of the file's bytes.
- `classify_changes(current: dict[str, str], previous: dict[str, str]) -> Changes` where `Changes` is a small dataclass/namedtuple with `added: set[str]`, `changed: set[str]`, `deleted: set[str]` (keys are repo-relative paths).

**Behavior:** `added` = in current not previous; `deleted` = in previous not current; `changed` = in both with differing hash. Pure functions over dicts (no walking here — the builder supplies the maps).

**Tests to add (failing first):**
- `hash_file` returns a stable 64-char hex string for a temp file and differs when contents differ.
- `classify_changes` with crafted dicts returns the correct added/changed/deleted sets, including the no-change case (all empty).

**Steps:** failing tests → implement → run (pass) → full suite green → ruff clean → commit (`feat: file content hashing and change classification`).

---

## Task 4: Embedder seam (`Embedder`, `FakeEmbedder`, `BgeSmallEmbedder`)

**Files:** Modify `src/index/embeddings.py`; tests `tests/unit/test_embeddings_embedder.py`, plus one marked real-model test.

**Interface:**
- `Embedder` — a `typing.Protocol` with `embed_texts(self, texts: list[str]) -> list[list[float]]`.
- `FakeEmbedder` — deterministic: maps each text to a fixed-dim (e.g. 16) unit-normalized vector derived from a hash of the text, so identical text → identical vector and different text → (almost surely) different vector. No I/O, no model.
- `BgeSmallEmbedder` — wraps `sentence_transformers.SentenceTransformer("BAAI/bge-small-en-v1.5")`, returns normalized vectors as `list[list[float]]`. Lazy-load the model on first use. No query prefix by default.

**Tests to add (failing first):**
- `FakeEmbedder().embed_texts(["a", "b", "a"])` → 3 vectors, all same length; vector[0] == vector[2]; vector[0] != vector[1]; each is unit-normalized (L2 ≈ 1).
- A real-model test for `BgeSmallEmbedder` that **self-skips** unless `os.environ.get("DOCSMITH_RUN_MODEL_TESTS") == "1"` (use `pytest.mark.skipif`), so plain `pytest`/CI never downloads the model. When enabled, it asserts the model embeds two related sentences with higher cosine similarity than two unrelated ones.

**Steps:** failing tests → implement the protocol + both embedders → run (`FakeEmbedder` tests pass; real-model test skipped) → full suite green → ruff clean → commit (`feat: embedder protocol with fake and bge-small implementations`).

---

## Task 5: `VectorStore` Chroma wrapper

**Files:** Modify `src/index/embeddings.py`; test `tests/unit/test_vector_store.py`.

**Interface:** `VectorStore(embedder: Embedder, persist_dir: str)` per the Data Contracts:
- `add(group: str, items: list[tuple[str, str, str]]) -> None` — items are `(id, text, file)`; embeds texts via the embedder and upserts into the Chroma collection with metadata `{"group", "file"}`.
- `query(query_text: str, group: str, top_k: int) -> list[tuple[str, float]]` — returns `(id, similarity)` pairs within `group`, similarity = `1 - distance`, sorted descending, length ≤ top_k.
- `delete_by_files(files: set[str]) -> None`.
- `reset() -> None`.

**Behavior:** collection created with `metadata={"hnsw:space": "cosine"}`. Use the injected `Embedder` (tests pass `FakeEmbedder`) — do NOT hardcode bge. Persist under `persist_dir` (tests use `tmp_path`).

**Tests to add (failing first), using `FakeEmbedder` + a `tmp_path` persist dir:**
- After `add("symbol", [("a.py::foo","foo bar","a.py"), ("b.py::baz","totally different","b.py")])`, `query("foo bar", "symbol", top_k=5)` returns `a.py::foo` as the top hit with similarity ≈ 1.0 (identical text), and `b.py::baz` lower.
- `query` respects `group` (a section-group item is not returned when querying `"symbol"`).
- `delete_by_files({"a.py"})` removes `a.py::foo`; a subsequent query no longer returns it.
- Similarity is in `[0, 1]` and ordered descending (guards the `1 - distance` conversion).

**Steps:** failing tests → implement wrapper → run (pass) → full suite green → ruff clean → commit (`feat: cosine Chroma vector store wrapper`).

---

## Task 6: Embedding linking + hybrid merge

**Files:** Modify `src/index/linker.py`; test `tests/unit/test_linker_hybrid.py`.

**Interface:**
- `link_by_embedding(sections: dict[str, DocSection], store: VectorStore, section_text: Callable[[DocSection], str], top_k: int, threshold: float) -> list[Link]` — for each section, `store.query(section_text(section), "symbol", top_k)`, keep hits with similarity ≥ threshold, emit `Link(symbol_id=hit_id, section_id=section.id, via="embedding", score=similarity)`.
- `merge_links(symbol_links: list[Link], embedding_links: list[Link]) -> list[Link]` — union by `(symbol_id, section_id)`; a pair present in both becomes one `Link(via="both", score=1.0)`; symbol-only stays `symbol-match`/`1.0`; embedding-only stays `embedding`/its score. Deterministic ordering (e.g. symbol-match first, then remaining embedding links).

**Tests to add (failing first):** (use `FakeEmbedder`-backed `VectorStore` seeded with a couple of symbols, or a tiny fake store)
- `link_by_embedding` only emits links above threshold and at most `top_k` per section; `via=="embedding"`, score in `[0,1]`.
- `merge_links`: overlapping pair → single `via=="both"`, `score==1.0`; symbol-only and embedding-only pairs preserved with correct `via`/score; no duplicate `(symbol_id, section_id)` pairs in the output.

**Steps:** failing tests → implement both functions → run (pass) → full suite green → ruff clean → commit (`feat: embedding recall linking and hybrid merge`).

---

## Task 7: Wire embeddings + hybrid linking into `build_index`

**Files:** Modify `src/index/builder.py`; test `tests/integration/test_build_index_hybrid.py`.

**Interface:** `build_index(repo_root, output_path=None, *, embeddings=True, full=False) -> Index`.

**Behavior:**
- Walk + parse as today, but pass `rel_path=os.path.relpath(path, repo_root)` to the parsers so ids/files are repo-relative. Populate `index.file_hashes` (via `hash_file`) for every indexed file.
- If `embeddings` is True: resolve the embedder (`embedder or BgeSmallEmbedder()`), construct a `VectorStore` (persist dir derived from `output_path` or `.docsmith/chroma/`); `add("symbol", ...)` for all symbols and `add("section", ...)` for all sections (text via the builders); compute `symbol_links = link_by_name(...)`, `embedding_links = link_by_embedding(...)`, `index.links = merge_links(...)`. The `embedder` param (see Data Contracts) is the injection seam — integration tests pass `FakeEmbedder()`.
- If `embeddings` is False (`--no-embeddings`): skip the vector store; `index.links = link_by_name(...)` only.
- `full=True`: `VectorStore.reset()` before adding (clean rebuild).
- Persist via `save_index` when `output_path` given.

**Tests to add (failing first), injecting `FakeEmbedder`:**
- `build_index("tests/fixtures/sample_repo", embeddings=True, <fake embedder>)` → ids are repo-relative (e.g. a symbol with `id == "app.py::create_user"`); `index.file_hashes` has an entry for `app.py` and `README.md`; `index.links` includes `via in {"symbol-match","both"}` for the Users→create_user pair; at least one `via=="embedding"` or `"both"` link exists.
- `embeddings=False` → all links are `via=="symbol-match"` and `index.links` equals the pure symbol-match result.
- No duplicate `(symbol_id, section_id)` pairs across `index.links`.

**Steps:** failing tests → implement wiring + injection seam → run (pass) → full suite green → ruff clean → commit (`feat: hybrid index build with embeddings and repo-relative ids`).

---

## Task 8: Incremental `update_index`

**Files:** Modify `src/index/builder.py`; test `tests/integration/test_update_index.py`.

**Interface:** `update_index(repo_root, output_path, *, embeddings=True) -> Index` (loads the existing index at `output_path`).

**Behavior:**
1. `load_index(output_path)`; build the current `path → hash` map by walking + hashing.
2. `classify_changes(current, previous=index.file_hashes)`.
3. Remove symbols/sections whose `file` is in `changed ∪ deleted`; `VectorStore.delete_by_files(changed ∪ deleted)`.
4. Re-parse + (if embeddings) re-embed + add files in `added ∪ changed` only.
5. Update `index.file_hashes` to `current`.
6. **Recompute links fully** (`link_by_name` + `link_by_embedding` over current sections/symbols, then `merge_links`).
7. `save_index`; `log` the added/changed/deleted counts.

**Tests to add (failing first), injecting `FakeEmbedder`, using a `tmp_path` copy of the fixture repo:**
- Build once; then modify one file's contents and `update_index` → the index reflects the new content; `file_hashes` updated; a spy/fake embedder records that ONLY the changed file's entities were re-embedded (assert the re-embedded ids belong only to the changed file).
- Add a new file → its symbols appear after update. Delete a file → its symbols/sections and vectors are gone, and no links reference them.
- Links are correct and contain no dangling `symbol_id`/`section_id` after updates.

**Steps:** failing tests → implement `update_index` → run (pass) → full suite green → ruff clean → commit (`feat: incremental index updates via content hashing`).

---

## Task 9: CLI — incremental-by-default, `--full`, `--no-embeddings`

**Files:** Modify `docsmith.py`; test `tests/integration/test_cli_build_index.py` (extend).

**Behavior:** the `build-index` subcommand gains:
- `--full` (store_true) and `--no-embeddings` (store_true).
- Dispatch logic: if `--full` OR no index exists at `--output` → `build_index(repo, output_path=out, embeddings=not no_embeddings, full=full)`. Else (index exists, not `--full`) → `update_index(repo, out, embeddings=not no_embeddings)`.
- Keep the one-line summary; when updating, also print the added/changed/deleted counts.
- The CLI default uses the real `BgeSmallEmbedder`. To keep the CLI test offline, the CLI test runs with `--no-embeddings` (so no model download).

**Tests to add (failing first), via `subprocess` with `cwd=repo root`:**
- `build-index --repo tests/fixtures/sample_repo --output <tmp> --no-embeddings` → exit 0, file exists, JSON has `symbols`/`sections`/`links`/`file_hashes`, a symbol named `create_user`, and all links `via=="symbol-match"`.
- Running the same command a second time (index now exists) still exits 0 and produces a valid index (exercises the incremental-by-default path with `--no-embeddings`).

**Steps:** failing tests → implement flags + dispatch → run (pass) → full suite green → ruff clean → commit (`feat: incremental-by-default build-index CLI with --full/--no-embeddings`).

---

## Definition of Done

- `build_index` produces hybrid links (`symbol-match` + `embedding` merged to `both`) using a local embedder; ids are repo-relative; `file_hashes` populated.
- `update_index` re-processes only added/changed files (verified: only those re-embedded), prunes deleted ones, and recomputes links with no dangling references.
- `--no-embeddings` yields symbol-match-only links; `--full` forces a clean rebuild incl. the Chroma collection.
- All embedding/linking/incremental logic is tested with a `FakeEmbedder` — `pytest` runs fully offline; the real bge-small test self-skips unless `DOCSMITH_RUN_MODEL_TESTS=1`.
- Full `pytest` suite green; `ruff check .` clean; CI runs the full suite.
