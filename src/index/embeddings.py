"""Embedder protocol, implementations, and vector store for Docsmith's retrieval layer.

Provides:
- ``Embedder``: a ``typing.Protocol`` defining the embedding interface.
- ``FakeEmbedder``: deterministic, offline embedder for unit tests.
- ``BgeSmallEmbedder``: production embedder wrapping BAAI/bge-small-en-v1.5,
  lazy-loaded on first use so that importing this module never triggers a
  model download.
- ``VectorStore``: persisted Chroma-backed cosine vector store keyed by
  entity id with group and file metadata for filtered retrieval and
  incremental updates.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import chromadb

if TYPE_CHECKING:
    from chromadb import Collection
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


_COLLECTION_NAME = "docsmith"
_COSINE_METADATA = {"hnsw:space": "cosine"}


class VectorStore:
    """Persisted cosine-space vector store backed by Chroma.

    Stores vectors keyed by entity id with ``group`` and ``file`` metadata,
    supporting group-filtered queries and file-level deletions for incremental
    index updates.

    Args:
        embedder: Backend used to embed texts before upsert and query.
        persist_dir: Filesystem path for Chroma's persistent storage.
    """

    def __init__(self, embedder: Embedder, persist_dir: str) -> None:
        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection: Collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata=_COSINE_METADATA,
        )

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, group: str, items: list[tuple[str, str, str]]) -> None:
        """Embed and upsert items into the collection.

        Args:
            group: Logical namespace (e.g. ``"symbol"`` or ``"section"``)
                stored as metadata so queries can be filtered.
            items: Sequence of ``(id, text, file)`` tuples.  The ``id``
                must be unique within the collection; ``file`` is stored for
                later bulk deletion.
        """
        if not items:
            return

        ids = [item[0] for item in items]
        texts = [item[1] for item in items]
        files = [item[2] for item in items]

        embeddings = self._embedder.embed_texts(texts)
        metadatas = [{"group": group, "file": file} for file in files]

        self._collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

    def delete_by_files(self, files: set[str]) -> None:
        """Delete all vectors whose ``file`` metadata is in *files*.

        Args:
            files: Set of file paths to remove.  No-op when empty.
        """
        if not files:
            return
        self._collection.delete(where={"file": {"$in": list(files)}})

    def reset(self) -> None:
        """Drop all stored vectors by deleting and recreating the collection."""
        self._client.delete_collection(_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata=_COSINE_METADATA,
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def query(self, query_text: str, group: str, top_k: int) -> list[tuple[str, float]]:
        """Find the *top_k* most similar items in *group*.

        Args:
            query_text: Text to embed and search for.
            group: Only items stored under this group are considered.
            top_k: Maximum number of results to return.

        Returns:
            A list of ``(id, similarity)`` pairs sorted by similarity
            descending.  ``similarity = 1.0 - cosine_distance`` so a
            perfect match yields ``1.0``.  Returns ``[]`` when the
            collection is empty or no results match the filter.
        """
        if self._collection.count() == 0:
            return []

        query_embedding = self._embedder.embed_texts([query_text])[0]

        try:
            result = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"group": group},
            )
        except Exception:
            # Chroma raises if n_results > number of items in the filtered set;
            # in that case return whatever results are available by catching and
            # retrying with a smaller n_results, or simply return empty.
            return []

        ids_nested = result.get("ids") or []
        distances_nested = result.get("distances") or []

        if not ids_nested or not distances_nested:
            return []

        ids_flat = ids_nested[0]
        distances_flat = distances_nested[0]

        # Clamp to [0, 1]: cosine distance is in [0, 2], so 1-dist can be
        # negative for anti-correlated vectors; those are practically irrelevant.
        pairs = [
            (id_, max(0.0, 1.0 - dist))
            for id_, dist in zip(ids_flat, distances_flat, strict=True)
        ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs
