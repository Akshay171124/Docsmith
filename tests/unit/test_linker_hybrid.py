"""Unit tests for link_by_embedding and merge_links in src.index.linker.

Tests cover:
- link_by_embedding: threshold filtering, via/score fields, top_k cap per section.
- merge_links: union semantics, via="both" on overlap, ordering guarantee.
"""

from __future__ import annotations

import pytest

from src.models import DocSection, Link  # noqa: E402 — kept after __future__ per isort

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_section(
    raw: str,
    *,
    section_id: str = "docs/guide.md#usage",
    file: str = "docs/guide.md",
) -> DocSection:
    """Return a minimal DocSection whose raw text is *raw*."""
    return DocSection(
        id=section_id,
        heading_path=("Usage",),
        file=file,
        raw=raw,
        start_line=1,
        end_line=10,
        referenced_symbols=(),
        referenced_config_keys=(),
    )


def make_link(symbol_id: str, section_id: str, via: str, score: float = 1.0) -> Link:
    """Return a Link with the given fields."""
    return Link(symbol_id=symbol_id, section_id=section_id, via=via, score=score)


# ---------------------------------------------------------------------------
# link_by_embedding tests
# ---------------------------------------------------------------------------


class TestLinkByEmbedding:
    """Tests for link_by_embedding using a real VectorStore + FakeEmbedder."""

    def _make_store(self, tmp_path):
        from src.index.embeddings import FakeEmbedder, VectorStore

        return VectorStore(FakeEmbedder(), str(tmp_path))

    def test_identical_text_emits_link_at_high_threshold(self, tmp_path):
        """A section whose text is identical to a stored symbol text gets similarity ≈ 1.0
        and survives even a high threshold (0.99)."""
        from src.index.linker import link_by_embedding

        store = self._make_store(tmp_path)
        symbol_text = "initialize the database connection pool"
        store.add("symbol", [("sym::init_db", symbol_text, "src/db.py")])

        section = make_section(symbol_text, section_id="docs/setup.md#db")
        sections = {section.id: section}

        links = link_by_embedding(sections, store, lambda s: s.raw, top_k=5, threshold=0.99)

        assert len(links) == 1
        link = links[0]
        assert link.symbol_id == "sym::init_db"
        assert link.section_id == "docs/setup.md#db"
        assert link.via == "embedding"
        assert link.score >= 0.99
        assert link.score <= 1.0

    def test_unrelated_section_dropped_at_high_threshold(self, tmp_path):
        """A section with unrelated text is dropped when threshold is 0.99."""
        from src.index.linker import link_by_embedding

        store = self._make_store(tmp_path)
        store.add("symbol", [("sym::render_chart", "render the bar chart widget", "src/ui.py")])

        # Totally unrelated text — FakeEmbedder uses SHA-256 seeding so this
        # will have a very different vector from the stored symbol.
        section = make_section("configure logging output format", section_id="docs/logging.md#fmt")
        sections = {section.id: section}

        links = link_by_embedding(sections, store, lambda s: s.raw, top_k=5, threshold=0.99)

        assert links == []

    def test_low_threshold_emits_links(self, tmp_path):
        """With threshold=0.0, all returned hits (including weak ones) become Links."""
        from src.index.linker import link_by_embedding

        store = self._make_store(tmp_path)
        store.add(
            "symbol",
            [
                ("sym::alpha", "alpha function for processing", "src/core.py"),
                ("sym::beta", "beta function for validation", "src/core.py"),
            ],
        )

        section = make_section("alpha function for processing", section_id="docs/api.md#alpha")
        sections = {section.id: section}

        links = link_by_embedding(sections, store, lambda s: s.raw, top_k=2, threshold=0.0)

        assert len(links) >= 1
        for link in links:
            assert link.via == "embedding"
            assert 0.0 <= link.score <= 1.0
            assert link.section_id == "docs/api.md#alpha"

    def test_top_k_caps_results_per_section(self, tmp_path):
        """At most top_k links are emitted per section."""
        from src.index.linker import link_by_embedding

        store = self._make_store(tmp_path)
        # Add 5 symbols
        symbols = [(f"sym::{i}", f"symbol text number {i}", "src/x.py") for i in range(5)]
        store.add("symbol", symbols)

        section = make_section("symbol text", section_id="docs/ref.md#all")
        sections = {section.id: section}

        links = link_by_embedding(sections, store, lambda s: s.raw, top_k=2, threshold=0.0)

        assert len(links) <= 2

    def test_all_emitted_links_have_embedding_via(self, tmp_path):
        """Every Link produced by link_by_embedding has via=='embedding'."""
        from src.index.linker import link_by_embedding

        store = self._make_store(tmp_path)
        text = "parse the configuration file into a settings object"
        store.add("symbol", [("sym::parse_config", text, "src/config.py")])

        section = make_section(text, section_id="docs/config.md#parsing")
        sections = {section.id: section}

        links = link_by_embedding(sections, store, lambda s: s.raw, top_k=3, threshold=0.0)

        assert all(link.via == "embedding" for link in links)

    def test_empty_store_returns_no_links(self, tmp_path):
        """When the store has no symbols, link_by_embedding returns []."""
        from src.index.linker import link_by_embedding

        store = self._make_store(tmp_path)
        section = make_section("some section text", section_id="docs/x.md#y")
        sections = {section.id: section}

        links = link_by_embedding(sections, store, lambda s: s.raw, top_k=5, threshold=0.0)

        assert links == []


# ---------------------------------------------------------------------------
# merge_links tests
# ---------------------------------------------------------------------------


class TestMergeLinks:
    """Tests for merge_links — pure logic, no store needed."""

    def test_overlap_becomes_both(self):
        """A (symbol_id, section_id) pair present in both lists → via='both', score=1.0."""
        from src.index.linker import merge_links

        sym = make_link("sym::foo", "docs/x.md#s", "symbol-match", 1.0)
        emb = make_link("sym::foo", "docs/x.md#s", "embedding", 0.75)

        result = merge_links([sym], [emb])

        assert len(result) == 1
        assert result[0].via == "both"
        assert result[0].score == pytest.approx(1.0)
        assert result[0].symbol_id == "sym::foo"
        assert result[0].section_id == "docs/x.md#s"

    def test_symbol_only_pair_preserved(self):
        """A pair only in symbol_links is kept with via='symbol-match'."""
        from src.index.linker import merge_links

        sym = make_link("sym::bar", "docs/y.md#s", "symbol-match", 1.0)

        result = merge_links([sym], [])

        assert len(result) == 1
        assert result[0].via == "symbol-match"
        assert result[0].score == pytest.approx(1.0)

    def test_embedding_only_pair_preserved(self):
        """A pair only in embedding_links is kept with its original score."""
        from src.index.linker import merge_links

        emb = make_link("sym::baz", "docs/z.md#s", "embedding", 0.63)

        result = merge_links([], [emb])

        assert len(result) == 1
        assert result[0].via == "embedding"
        assert result[0].score == pytest.approx(0.63)

    def test_no_duplicate_pairs(self):
        """Output has no duplicate (symbol_id, section_id) pairs."""
        from src.index.linker import merge_links

        sym = make_link("sym::foo", "docs/x.md#s", "symbol-match")
        emb1 = make_link("sym::foo", "docs/x.md#s", "embedding", 0.8)
        emb2 = make_link("sym::other", "docs/x.md#s", "embedding", 0.5)

        result = merge_links([sym], [emb1, emb2])

        keys = [(link.symbol_id, link.section_id) for link in result]
        assert len(keys) == len(set(keys))

    def test_ordering_symbol_before_embedding_only(self):
        """Symbol-match/both pairs come before embedding-only pairs in the output."""
        from src.index.linker import merge_links

        sym1 = make_link("sym::a", "docs/a.md#s", "symbol-match")
        sym2 = make_link("sym::b", "docs/b.md#s", "symbol-match")
        emb_only = make_link("sym::c", "docs/c.md#s", "embedding", 0.5)

        result = merge_links([sym1, sym2], [emb_only])

        assert len(result) == 3
        # First two should be symbol-match (or both), last is embedding-only
        assert result[0].via in ("symbol-match", "both")
        assert result[1].via in ("symbol-match", "both")
        assert result[2].via == "embedding"

    def test_both_pair_appears_in_symbol_match_position(self):
        """A 'both' pair occupies the position of the original symbol-match entry."""
        from src.index.linker import merge_links

        sym1 = make_link("sym::first", "docs/a.md#s", "symbol-match")
        sym2 = make_link("sym::second", "docs/b.md#s", "symbol-match")
        # sym2 also has an embedding hit
        emb = make_link("sym::second", "docs/b.md#s", "embedding", 0.9)
        emb_only = make_link("sym::third", "docs/c.md#s", "embedding", 0.4)

        result = merge_links([sym1, sym2], [emb, emb_only])

        assert len(result) == 3
        # sym1 stays symbol-match
        assert result[0].symbol_id == "sym::first"
        assert result[0].via == "symbol-match"
        # sym2 upgraded to both
        assert result[1].symbol_id == "sym::second"
        assert result[1].via == "both"
        # embedding-only comes last
        assert result[2].symbol_id == "sym::third"
        assert result[2].via == "embedding"

    def test_empty_both_inputs(self):
        """merge_links with two empty lists returns an empty list."""
        from src.index.linker import merge_links

        assert merge_links([], []) == []

    def test_input_order_within_symbol_group_preserved(self):
        """Input order within the symbol-match group is preserved in the output."""
        from src.index.linker import merge_links

        syms = [make_link(f"sym::{i}", f"docs/{i}.md#s", "symbol-match") for i in range(4)]

        result = merge_links(syms, [])

        assert [link.symbol_id for link in result] == [f"sym::{i}" for i in range(4)]

    def test_input_order_within_embedding_only_group_preserved(self):
        """Input order within the embedding-only group is preserved in the output."""
        from src.index.linker import merge_links

        embs = [
            make_link(f"sym::e{i}", f"docs/e{i}.md#s", "embedding", 0.5) for i in range(3)
        ]

        result = merge_links([], embs)

        assert [link.symbol_id for link in result] == [f"sym::e{i}" for i in range(3)]
