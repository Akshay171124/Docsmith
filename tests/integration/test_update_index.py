"""Integration tests for update_index — incremental re-indexing via content hashing."""

from __future__ import annotations

import shutil

import pytest

from src.index.builder import build_index, update_index
from src.index.embeddings import FakeEmbedder

FIXTURE_REPO = "tests/fixtures/sample_repo"


class RecordingEmbedder(FakeEmbedder):
    """FakeEmbedder that records texts passed to embed_texts via store.add().

    ``VectorStore.add()`` always calls embed_texts with a batch of N>=2 texts
    (one per entity being upserted).  ``VectorStore.query()`` always calls it
    with exactly 1 text (the query vector).  We exploit this to distinguish
    add calls (batch > 1) from query calls (batch == 1) and record only the
    former, which are the texts being inserted into the vector store.

    Call ``clear()`` to reset the record between build and update phases.
    """

    def __init__(self) -> None:
        super().__init__()
        self.added_texts: list[str] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # store.add() always calls embed_texts with the full batch of items
        # (len >= 1 but in practice >= 2 for any real file with multiple symbols).
        # store.query() always calls it with exactly 1 text.
        # We record all calls so we can inspect them; the test filters on len.
        if len(texts) != 1:
            # Batch upsert — these are the texts being added to the store
            self.added_texts.extend(texts)
        return super().embed_texts(texts)

    def clear(self) -> None:
        self.added_texts = []


@pytest.fixture()
def tmp_repo(tmp_path):
    """Copy the sample_repo fixture into a writable tmp directory."""
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE_REPO, dest)
    return dest


def _output_path(tmp_path, name="index.json"):
    return str(tmp_path / name)


# ---------------------------------------------------------------------------
# Test 1: Changed file is reflected in the updated index
# ---------------------------------------------------------------------------


def test_changed_file_reflected(tmp_path, tmp_repo):
    """Overwriting app.py adds brand_new_fn to symbols and updates its hash."""
    idx = _output_path(tmp_path)
    original_index = build_index(
        str(tmp_repo), output_path=idx, embeddings=True, embedder=FakeEmbedder()
    )
    original_hash = original_index.file_hashes["app.py"]

    # Append a new function to app.py
    app_py = tmp_repo / "app.py"
    app_py.write_text(app_py.read_text() + "\n\ndef brand_new_fn(): pass\n")

    updated = update_index(str(tmp_repo), idx, embeddings=True, embedder=FakeEmbedder())

    symbol_names = {sym.name for sym in updated.symbols.values()}
    assert "brand_new_fn" in symbol_names, (
        f"Expected 'brand_new_fn' in symbols after update. Got: {symbol_names}"
    )
    assert updated.file_hashes["app.py"] != original_hash, (
        "Hash for app.py should have changed after the file was modified"
    )


# ---------------------------------------------------------------------------
# Test 2: Only the changed file is re-embedded
# ---------------------------------------------------------------------------


def test_only_changed_file_re_embedded(tmp_path, tmp_repo):
    """After update, only entities from the changed file are re-embedded."""
    embedder = RecordingEmbedder()
    idx = _output_path(tmp_path)
    build_index(str(tmp_repo), output_path=idx, embeddings=True, embedder=embedder)

    # Reset the recording so we only observe the update phase
    embedder.clear()

    # Modify app.py
    app_py = tmp_repo / "app.py"
    app_py.write_text(app_py.read_text() + "\n\ndef brand_new_fn(): pass\n")

    update_index(str(tmp_repo), idx, embeddings=True, embedder=embedder)

    # added_texts are the batch upserts — only entities from changed files
    added = embedder.added_texts
    assert added, "Expected some texts to be added to the vector store during the update"

    app_tokens = {"create_user", "UserService", "deactivate", "brand_new_fn"}
    # Tokens unique to unchanged code files: service.ts and widget.js
    unchanged_tokens = {"formatName", "renderWidget"}

    for text in added:
        has_app_token = any(tok in text for tok in app_tokens)
        has_unchanged_token = any(tok in text for tok in unchanged_tokens)
        assert has_app_token or not has_unchanged_token, (
            f"Added embedding text looks like it came from an unchanged file: {text!r}"
        )

    # None of the unchanged-file-unique tokens should appear in added texts
    all_added = " ".join(added)
    for tok in unchanged_tokens:
        assert tok not in all_added, (
            f"Token {tok!r} from an unchanged file appeared in re-added embedding texts"
        )


# ---------------------------------------------------------------------------
# Test 3: Added file is indexed
# ---------------------------------------------------------------------------


def test_added_file_indexed(tmp_path, tmp_repo):
    """A new file created after the initial build is added to the index."""
    idx = _output_path(tmp_path)
    build_index(str(tmp_repo), output_path=idx, embeddings=True, embedder=FakeEmbedder())

    # Create a brand-new file
    (tmp_repo / "extra.py").write_text("def extra_fn(): pass\n")

    updated = update_index(str(tmp_repo), idx, embeddings=True, embedder=FakeEmbedder())

    symbol_names = {sym.name for sym in updated.symbols.values()}
    assert "extra_fn" in symbol_names, (
        f"Expected 'extra_fn' after adding extra.py. Got: {symbol_names}"
    )
    assert "extra.py" in updated.file_hashes, (
        "extra.py should appear in file_hashes after being indexed"
    )


# ---------------------------------------------------------------------------
# Test 4: Deleted file is pruned from the index
# ---------------------------------------------------------------------------


def test_deleted_file_pruned(tmp_path, tmp_repo):
    """Deleting service.ts removes its symbols and drops its hash key."""
    idx = _output_path(tmp_path)
    build_index(str(tmp_repo), output_path=idx, embeddings=True, embedder=FakeEmbedder())

    (tmp_repo / "service.ts").unlink()

    updated = update_index(str(tmp_repo), idx, embeddings=True, embedder=FakeEmbedder())

    # No symbols from service.ts
    stale_symbols = [sym for sym in updated.symbols.values() if sym.file == "service.ts"]
    assert not stale_symbols, (
        f"Found symbols from deleted service.ts: {[s.id for s in stale_symbols]}"
    )

    # No hash entry for deleted file
    assert "service.ts" not in updated.file_hashes, (
        "service.ts should not appear in file_hashes after deletion"
    )

    # No dangling link references
    _assert_no_dangling_links(updated)


# ---------------------------------------------------------------------------
# Test 5: No dangling references after any combination of changes
# ---------------------------------------------------------------------------


def test_no_dangling_references_after_update(tmp_path, tmp_repo):
    """After a mixed update (add + change + delete), all links are self-consistent."""
    idx = _output_path(tmp_path)
    build_index(str(tmp_repo), output_path=idx, embeddings=True, embedder=FakeEmbedder())

    # Delete one file, add another, modify a third
    (tmp_repo / "service.ts").unlink()
    (tmp_repo / "extra.py").write_text("def extra_fn(): pass\n")
    app_py = tmp_repo / "app.py"
    app_py.write_text(app_py.read_text() + "\n\ndef brand_new_fn(): pass\n")

    updated = update_index(str(tmp_repo), idx, embeddings=True, embedder=FakeEmbedder())

    _assert_no_dangling_links(updated)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _assert_no_dangling_links(index):
    """Assert every link references a symbol and section that exist in the index."""
    for link in index.links:
        assert link.symbol_id in index.symbols, (
            f"Link references missing symbol {link.symbol_id!r}"
        )
        assert link.section_id in index.sections, (
            f"Link references missing section {link.section_id!r}"
        )
