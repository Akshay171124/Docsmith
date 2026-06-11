# Changelog

All notable changes to Docsmith are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project predates its first
release; everything lives under **Unreleased** until then.

## [Unreleased]

### Added
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
