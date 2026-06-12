"""Unit tests for VectorStore (cosine Chroma wrapper).

Uses FakeEmbedder (deterministic, offline) and pytest's tmp_path fixture.
"""

from __future__ import annotations

import pytest

from src.index.embeddings import FakeEmbedder, VectorStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYMBOL_ITEMS = [
    ("a.py::foo", "foo bar baz", "a.py"),
    ("b.py::baz", "totally unrelated content", "b.py"),
]


@pytest.fixture()
def store(tmp_path):
    """A fresh VectorStore backed by a temporary Chroma directory."""
    return VectorStore(FakeEmbedder(), str(tmp_path))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_top_hit_is_identical_text(store):
    """Querying with the exact text of an item returns that item as rank-0."""
    store.add("symbol", SYMBOL_ITEMS)
    results = store.query("foo bar baz", "symbol", top_k=5)

    assert len(results) >= 1
    top_id, top_sim = results[0]
    assert top_id == "a.py::foo"
    # Identical text → identical vector → cosine distance ≈ 0 → similarity ≈ 1.0
    assert top_sim == pytest.approx(1.0, abs=1e-3)


def test_similarities_sorted_descending(store):
    """All returned similarities must be in [0, 1] and sorted descending."""
    store.add("symbol", SYMBOL_ITEMS)
    results = store.query("foo bar baz", "symbol", top_k=5)

    similarities = [sim for _, sim in results]
    assert similarities == sorted(similarities, reverse=True), "Not sorted descending"
    for sim in similarities:
        assert -1e-6 <= sim <= 1.0 + 1e-6, f"Similarity out of range: {sim}"


def test_group_filter_excludes_other_groups(store):
    """Items stored under a different group must not appear in query results."""
    store.add("symbol", SYMBOL_ITEMS)
    store.add("section", [("R.md#x", "foo bar baz", "R.md")])

    results = store.query("foo bar baz", "symbol", top_k=5)
    ids = [id_ for id_, _ in results]
    assert "R.md#x" not in ids


def test_delete_by_files_removes_items(store):
    """After deleting a file's vectors, its IDs no longer appear in results."""
    store.add("symbol", SYMBOL_ITEMS)
    store.delete_by_files({"a.py"})

    results = store.query("foo bar baz", "symbol", top_k=5)
    ids = [id_ for id_, _ in results]
    assert "a.py::foo" not in ids


def test_empty_store_returns_empty_list(tmp_path):
    """Querying a store with no documents must return an empty list."""
    store = VectorStore(FakeEmbedder(), str(tmp_path))
    results = store.query("anything", "symbol", top_k=5)
    assert results == []


def test_add_empty_items_is_noop(store):
    """add() with an empty list must not raise and must leave the store empty."""
    store.add("symbol", [])
    results = store.query("foo", "symbol", top_k=5)
    assert results == []


def test_delete_empty_files_is_noop(store):
    """delete_by_files() with an empty set must not raise."""
    store.add("symbol", SYMBOL_ITEMS)
    store.delete_by_files(set())  # should not raise
    results = store.query("foo bar baz", "symbol", top_k=5)
    assert len(results) > 0  # data still present


def test_reset_clears_all_data(store):
    """reset() must drop all stored vectors."""
    store.add("symbol", SYMBOL_ITEMS)
    store.reset()
    results = store.query("foo bar baz", "symbol", top_k=5)
    assert results == []


def test_top_k_zero_returns_empty_list(store):
    """query() with top_k=0 must return an empty list without hitting Chroma."""
    store.add("symbol", SYMBOL_ITEMS)
    results = store.query("foo bar baz", "symbol", top_k=0)
    assert results == []
