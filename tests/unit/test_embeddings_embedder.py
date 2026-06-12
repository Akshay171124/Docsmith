"""Unit tests for the Embedder protocol, FakeEmbedder, and BgeSmallEmbedder lazy-load."""

from __future__ import annotations

import math
import os

import pytest

from src.index.embeddings import BgeSmallEmbedder, Embedder, FakeEmbedder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _l2_norm(vec: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------------------
# FakeEmbedder tests
# ---------------------------------------------------------------------------


class TestFakeEmbedder:
    def test_returns_three_vectors_of_dim_16(self) -> None:
        embedder = FakeEmbedder()
        result = embedder.embed_texts(["a", "b", "a"])
        assert len(result) == 3
        for vec in result:
            assert len(vec) == 16

    def test_determinism_same_text_same_vector(self) -> None:
        embedder = FakeEmbedder()
        result = embedder.embed_texts(["a", "b", "a"])
        assert result[0] == result[2]

    def test_different_texts_different_vectors(self) -> None:
        embedder = FakeEmbedder()
        result = embedder.embed_texts(["a", "b", "a"])
        assert result[0] != result[1]

    def test_vectors_are_unit_normalized(self) -> None:
        embedder = FakeEmbedder()
        result = embedder.embed_texts(["hello", "world"])
        for vec in result:
            assert _l2_norm(vec) == pytest.approx(1.0, abs=1e-6)

    def test_implements_embedder_protocol(self) -> None:
        assert isinstance(FakeEmbedder(), Embedder)

    def test_cross_instance_determinism(self) -> None:
        """Two separate FakeEmbedder instances produce the same vector for the same text."""
        e1 = FakeEmbedder()
        e2 = FakeEmbedder()
        assert e1.embed_texts(["deterministic"])[0] == e2.embed_texts(["deterministic"])[0]


# ---------------------------------------------------------------------------
# BgeSmallEmbedder lazy-load tests (offline, no real model required)
# ---------------------------------------------------------------------------


class TestBgeSmallEmbedderLazyLoad:
    def test_construction_does_not_load_model(self) -> None:
        embedder = BgeSmallEmbedder()
        # The model attribute must not be set until first embed_texts call.
        assert not hasattr(embedder, "_model") or embedder._model is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# BgeSmallEmbedder real-model tests (opt-in only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("DOCSMITH_RUN_MODEL_TESTS") != "1",
    reason="set DOCSMITH_RUN_MODEL_TESTS=1 to run real-model test",
)
class TestBgeSmallEmbedderRealModel:
    def test_semantic_similarity_ordering(self) -> None:
        embedder = BgeSmallEmbedder()
        cat_vec, kitten_vec, airplane_vec = embedder.embed_texts(["cat", "kitten", "airplane"])
        sim_cat_kitten = _dot(cat_vec, kitten_vec)
        sim_cat_airplane = _dot(cat_vec, airplane_vec)
        assert sim_cat_kitten > sim_cat_airplane

    def test_vectors_are_unit_normalized(self) -> None:
        embedder = BgeSmallEmbedder()
        vecs = embedder.embed_texts(["normalize me"])
        assert _l2_norm(vecs[0]) == pytest.approx(1.0, abs=1e-5)
