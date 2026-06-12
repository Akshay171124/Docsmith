# Retrieval Core (Week 2) — Design Spec

**Date:** 2026-06-12
**Status:** Approved (brainstorming complete) → ready for implementation planning
**Builds on:** Week 1 Index Core (`2026-06-11-self-healing-docs-design.md`, `2026-06-11-index-core.md`)

---

## 1. Goal & Scope

Add the embedding-based recall layer to the index and make the index incrementally
updatable, so doc↔code linking catches sections that describe behavior without naming a
symbol — while keeping the deterministic symbol-match links as the precision anchor.

**In scope:**
- Local embeddings (`BAAI/bge-small-en-v1.5`) of code symbols and doc sections.
- File-based Chroma vector store under `.docsmith/chroma/`.
- Hybrid linking: deterministic symbol-match + embedding recall, merged.
- Content-hash-based incremental index updates.
- Repo-relative id normalization (carried over from Week 1, item M1).

**Out of scope (own later sub-project):** API-reference (OpenAPI/route) and config/CLI/env
doc extractors.

**Non-goals:** No LLM calls (still pure/deterministic except for the embedding model,
which is a local, offline model). No detection/repair (Weeks 3–4).

---

## 2. What gets embedded

- **Symbol embedding text:** `"{kind} {qualified_name}\n{signature}\n{docstring}"`
  (docstring omitted when `None`). Captures the symbol's name, shape, and prose.
- **Doc section embedding text:** `"{heading}\n{raw}"`.
- **Model:** `BAAI/bge-small-en-v1.5` via `sentence-transformers`, run locally/offline.
- **Store:** a file-based Chroma collection persisted under `.docsmith/chroma/`. Vectors
  live in Chroma, NOT in the JSON index.

---

## 3. Hybrid linking

Two link sources, merged into the single `Index.links` list:

1. **Symbol-match (precision, unchanged from Week 1):** `link_by_name` →
   `via="symbol-match"`, `score=1.0`.
2. **Embedding recall (new):** for each doc section, query Chroma for the top-k most
   similar symbols with cosine similarity ≥ threshold → `via="embedding"`,
   `score=similarity`. Defaults: `embedding_similarity_threshold=0.55` (already in
   `configs/base.yaml`) and `top_k=5` (new config key added under `linking:` in this work).

**Merge rule:** a `(symbol_id, section_id)` pair found by both sources collapses to a
single `Link` with `via="both"`, `score=1.0` (symbol-match certainty wins). Each pair
appears at most once in `Index.links`.

---

## 4. Incremental updates (content-hash)

- `Index` gains `file_hashes: dict[str, str]` (repo-relative path → sha256 of file
  bytes), persisted in the JSON.
- **Update flow** (`update_index`):
  1. Hash every current source/doc file under the repo (respecting the same skip-dirs and
     supported-language / `.md` rules as the full build).
  2. Diff against stored `file_hashes` → classify **added / changed / deleted**.
  3. Remove all symbols, sections, and Chroma vectors belonging to deleted or changed
     files.
  4. Re-parse and re-embed only added + changed files; add their symbols/sections/vectors.
  5. Update `file_hashes`.
  6. **Recompute links fully** (symbol-match + embedding recall over the current
     symbols/sections). Linking is cheap relative to embedding; a full relink avoids
     subtle staleness where a changed symbol affects another section's recall.
- `log` a one-line summary of added/changed/deleted counts.

The expensive embedding computation is incremental (only changed files re-embedded); the
deterministic linking pass is a full recompute.

---

## 5. id normalization (carry-over M1)

File paths embedded in `Symbol.id`, `DocSection.id`, and the `file` fields become
**repo-relative** (`os.path.relpath(path, repo_root)`), so ids are stable regardless of
how `--repo` is provided (`.`, an absolute path, `./sub`). This changes Week-1 id formats
(e.g. `app.py::create_user` instead of the full fixture path); Week-1 tests are updated
accordingly. The index is rebuilt, so there is no migration concern.

---

## 6. Testability

Embedding models are heavy and CI runs offline, so the embedding layer is built behind a
seam:

- `embeddings.py` defines an **`Embedder` protocol** (`embed_texts(texts) -> list[vector]`).
- Default implementation: bge-small via `sentence-transformers`.
- Tests inject a **fake deterministic embedder** (e.g. hash-seeded vectors) so the entire
  hybrid-linking and incremental-update logic is unit-testable with **no model download**.
- One opt-in/marked integration test may exercise the real model locally (not in the
  default CI run).

The deterministic pieces (content hashing, added/changed/deleted classification, link
merge, id normalization) are tested without any embedder at all.

---

## 7. CLI

- `build-index` becomes **incremental by default** when an index already exists at
  `--output`: it re-hashes and calls `update_index`. If no index exists, it does a full
  build.
- `--full` forces a clean rebuild (ignore/replace any existing index + Chroma collection).
- `--no-embeddings` skips the embedding layer for fast, deterministic-only runs
  (symbol-match links only).

---

## 8. Components / Files

| File | Change |
|---|---|
| `src/index/embeddings.py` | Implement: `Embedder` protocol, `BgeSmallEmbedder` (sentence-transformers), and a Chroma collection wrapper (`add`, `query`, `delete` by file/id). |
| `src/index/linker.py` | Add `link_by_embedding(sections, embedder/store, top_k, threshold)` and `merge_links(symbol_links, embedding_links)`. Keep `link_by_name`. |
| `src/index/builder.py` | Content-hash tracking; `update_index(repo_root, output_path, ...)`; id normalization (repo-relative); wire embeddings + hybrid linking into `build_index`; `--no-embeddings` path. |
| `src/index/store.py` | Persist/load `file_hashes`. Chroma persistence handled by the embeddings wrapper, outside the JSON. |
| `src/models.py` | Add `Index.file_hashes: dict[str, str]` (default empty). |
| `docsmith.py` | Incremental-by-default; add `--full` and `--no-embeddings` flags. |
| `.github/workflows/ci.yml` | Fold in carried-over CI fixes: run `tests/integration` too; bump Node-20 actions. |

---

## 9. Testing strategy

- **Unit (fake embedder, no model):** embedding text construction; `link_by_embedding`
  with a fake store; `merge_links` (symbol-only, embedding-only, overlapping → `both`);
  content-hash classification (added/changed/deleted); id normalization; store round-trip
  of `file_hashes`.
- **Integration (fake embedder):** full `build_index` with hybrid links over the fixture
  repo; `update_index` after mutating/adding/deleting a fixture file re-processes only the
  affected files and yields a correct index; `--no-embeddings` produces symbol-match-only
  links; CLI incremental-by-default vs `--full`.
- **Optional real-model test:** marked/skippable; verifies bge-small loads and produces
  sensible similarity on a tiny example. Not in default CI.

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Embedding model download bloats CI / breaks offline | `Embedder` seam + fake embedder; real model only in a marked, non-CI test. |
| Embedding recall floods links with weak matches | top-k + similarity threshold (configurable); symbol-match remains precision anchor. |
| Incremental update drift (stale vectors/links) | Delete-before-readd per changed file; full relink each update. |
| Chroma persistence format churn | Treat `.docsmith/chroma/` as a rebuildable cache; `--full` always reconstructs it. |
| id format change breaks Week-1 tests | Update Week-1 tests as part of this work; index is rebuilt (no migration). |
