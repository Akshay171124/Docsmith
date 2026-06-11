# Changelog

All notable changes to Docsmith are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project predates its first
release; everything lives under **Unreleased** until then.

## [Unreleased]

### Added
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
- Locked embeddings to a local model (`BAAI/bge-small-en-v1.5`) — free, no API key.
- Rewrote the Week 1 plan to describe interfaces/behavior/tests instead of embedding full
  implementation code (code is written during execution).

### Fixed
- Shortened over-length stub docstrings to satisfy `ruff` line-length (CI was red).
