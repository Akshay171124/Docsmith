# Changelog

All notable changes to Docsmith are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project predates its first
release; everything lives under **Unreleased** until then.

## [Unreleased]

### Added
- **Retrieval Core (Week 2)** — embedding-based recall + incremental updates:
  - `Embedder` seam (`src/index/embeddings.py`): `Embedder` protocol, deterministic
    offline `FakeEmbedder` (for tests), and `BgeSmallEmbedder` wrapping
    `BAAI/bge-small-en-v1.5` (lazy-loaded — importing never downloads the model).
  - Cosine `VectorStore` (Chroma, file-based): per-entity vectors with `group`/`file`
    metadata, `1 - distance` similarity, delete-by-file, reset.
  - Hybrid linking (`src/index/linker.py`): `link_by_embedding` (recall) + `merge_links`
    collapsing symbol-match ∩ embedding pairs to `via="both"`.
  - Content-hash incremental updates: `Index.file_hashes`, `src/index/hashing.py`
    (`hash_file`/`classify_changes`), and `update_index` that re-parses/re-embeds only
    added/changed files, prunes deleted ones, and recomputes links.
  - Repo-relative id normalization (resolves Week-1 carry-over M1).
  - CLI: `build-index` is incremental-by-default with `--full` and `--no-embeddings`.
  - All embedding/linking/incremental logic tested via `FakeEmbedder` (offline); the real
    bge-small test is gated behind `DOCSMITH_RUN_MODEL_TESTS=1`. 110 tests passing.
- **Index Core (Week 1)** — the deterministic, zero-LLM foundation:
  - Core data models: `Symbol`, `DocSection`, `Link`, `Index` (`src/models.py`).
  - Language registry with tree-sitter symbol queries for Python, TypeScript, JavaScript,
    and Go (`src/parsing/languages.py`).
  - Code parser extracting functions/classes/methods (with Python docstrings) via
    tree-sitter (`src/parsing/code_parser.py`).
  - Markdown doc parser splitting by heading and extracting symbol/config-key references
    (`src/parsing/doc_parser.py`).
  - Deterministic symbol↔section linker by name (`src/index/linker.py`).
  - JSON index persistence with tuple-preserving round-trip (`src/index/store.py`).
  - Index builder that walks a repo, parses code + docs, links, and writes
    `.docsmith/index.json` (`src/index/builder.py`); disambiguates colliding ids.
  - `docsmith.py build-index` CLI subcommand.
  - 45 passing tests (unit + integration); fixture repo spanning four languages + markdown.
- Design spec for the self-healing documentation system
  (`docs/superpowers/specs/2026-06-11-self-healing-docs-design.md`).
- Forge-inspired repository scaffolding: `src/` (parsing, index, detection, repair,
  github, llm, utils), `tests/`, `evaluation/`, `configs/`, `scripts/`, `docs/`.
- Project tooling: `pyproject.toml`, `requirements.txt`, `Dockerfile`, `action.yml`,
  `.pre-commit-config.yaml`, `.env.example`, `.claude/CLAUDE.md`.
- GitHub Actions CI workflow (`ruff` + `pytest`).
- Week 1 implementation plan — Index Core
  (`docs/superpowers/plans/2026-06-11-index-core.md`).
- Living project docs: `docs/planning/roadmap.md` (progress tracker) and this changelog.
- CI smoke test verifying the `src` package imports.

### Changed
- CI now runs the full test suite (was unit-only) and opts into Node 24.
- Locked embeddings to a local model (`BAAI/bge-small-en-v1.5`) — free, no API key.
- Rewrote the Week 1 plan to describe interfaces/behavior/tests instead of embedding full
  implementation code (code is written during execution).

### Fixed
- `build_index` always resets the vector store on a clean build, preventing orphaned
  vectors (and resulting dangling embedding links) when a stale Chroma collection outlives
  its JSON index.
- Shortened over-length stub docstrings to satisfy `ruff` line-length (CI was red).
