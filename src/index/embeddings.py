"""Embedder protocol and implementations for Docsmith's retrieval layer.

Provides:
- ``Embedder``: a ``typing.Protocol`` defining the embedding interface.
- ``FakeEmbedder``: deterministic, offline embedder for unit tests.
- ``BgeSmallEmbedder``: production embedder wrapping BAAI/bge-small-en-v1.5,
  lazy-loaded on first use so that importing this module never triggers a
  model download.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

DIM = 16  # Dimension used by FakeEmbedder


@runtime_checkable
class Embedder(Protocol):
    """Protocol for text embedding backends."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into fixed-dimension float vectors.

        Args:
            texts: Strings to embed.

        Returns:
            A list of L2-normalised float vectors, one per input text.
        """
        ...


class FakeEmbedder:
    """Deterministic, dependency-free embedder for use in tests.

    Produces a 16-dimensional unit vector for each text by seeding Python's
    ``random.Random`` from the SHA-256 digest of the text.  Identical texts
    always yield identical vectors; distinct texts (almost surely) differ.
    """

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts to deterministic unit vectors.

        Args:
            texts: Strings to embed.

        Returns:
            A list of L2-normalised 16-dimensional float vectors.
        """
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).hexdigest()
            rng = random.Random(digest)
            raw = [rng.gauss(0.0, 1.0) for _ in range(DIM)]
            norm = math.sqrt(sum(x * x for x in raw))
            results.append([x / norm for x in raw])
        return results


class BgeSmallEmbedder:
    """Production embedder wrapping ``BAAI/bge-small-en-v1.5``.

    The underlying ``SentenceTransformer`` model is lazy-loaded on the first
    call to ``embed_texts``; constructing an instance or importing this module
    never triggers a model download.
    """

    _model: SentenceTransformer | None

    def __init__(self) -> None:
        self._model = None  # model is loaded on first embed_texts call

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using the BGE-small model with L2 normalisation.

        Args:
            texts: Strings to embed.

        Returns:
            A list of L2-normalised 384-dimensional float vectors.
        """
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self._model = SentenceTransformer("BAAI/bge-small-en-v1.5")

        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in embeddings]
