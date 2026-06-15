"""Integration tests for hybrid build_index: embeddings, repo-relative ids, file_hashes."""

from __future__ import annotations

import os
import pathlib
import shutil

from src.index.builder import build_index
from src.index.embeddings import FakeEmbedder
from src.index.linker import link_by_name

FIXTURE_REPO = "tests/fixtures/sample_repo"


class TestHybridBuildIndex:
    """Tests for build_index with embeddings=True and repo-relative ids."""

    def test_symbol_ids_are_repo_relative(self, tmp_path: pathlib.Path) -> None:
        """Symbol ids use repo-relative paths, not absolute/fixture paths."""
        index = build_index(
            FIXTURE_REPO,
            output_path=str(tmp_path / "index.json"),
            embeddings=True,
            embedder=FakeEmbedder(),
        )

        assert "app.py::create_user" in index.symbols, (
            f"Expected 'app.py::create_user' in symbols. Got: {list(index.symbols)[:10]}"
        )

    def test_no_symbol_id_contains_fixture_path(self, tmp_path: pathlib.Path) -> None:
        """No symbol id contains the fixture directory prefix."""
        index = build_index(
            FIXTURE_REPO,
            output_path=str(tmp_path / "index.json"),
            embeddings=True,
            embedder=FakeEmbedder(),
        )

        for sym_id in index.symbols:
            assert "tests/fixtures" not in sym_id, (
                f"Symbol id {sym_id!r} contains absolute/fixture path"
            )

    def test_file_hashes_keys_are_repo_relative(self, tmp_path: pathlib.Path) -> None:
        """file_hashes maps repo-relative keys to 64-char hex strings."""
        index = build_index(
            FIXTURE_REPO,
            output_path=str(tmp_path / "index.json"),
            embeddings=True,
            embedder=FakeEmbedder(),
        )

        assert "app.py" in index.file_hashes, (
            f"Expected 'app.py' in file_hashes. Keys: {list(index.file_hashes)}"
        )
        assert "README.md" in index.file_hashes, (
            f"Expected 'README.md' in file_hashes. Keys: {list(index.file_hashes)}"
        )
        for rel, digest in index.file_hashes.items():
            assert len(digest) == 64, (
                f"file_hashes[{rel!r}] has length {len(digest)}, expected 64"
            )
            assert all(c in "0123456789abcdef" for c in digest), (
                f"file_hashes[{rel!r}] is not a hex string: {digest!r}"
            )

    def test_users_section_linked_to_create_user(self, tmp_path: pathlib.Path) -> None:
        """The Users section is linked to create_user via symbol-match or both."""
        index = build_index(
            FIXTURE_REPO,
            output_path=str(tmp_path / "index.json"),
            embeddings=True,
            embedder=FakeEmbedder(),
        )

        users_section_ids = {
            sec_id
            for sec_id, sec in index.sections.items()
            if sec.heading_path == ("Users",)
        }
        assert users_section_ids, "No 'Users' section found in index"

        linked_pairs = {(link.symbol_id, link.section_id): link.via for link in index.links}

        found = False
        for sec_id in users_section_ids:
            pair = ("app.py::create_user", sec_id)
            if pair in linked_pairs:
                via = linked_pairs[pair]
                assert via in {"symbol-match", "both"}, (
                    f"Expected via in {{'symbol-match', 'both'}}, got {via!r}"
                )
                found = True
                break

        assert found, (
            f"No link from 'app.py::create_user' to any Users section. "
            f"Links: {[(lnk.symbol_id, lnk.section_id, lnk.via) for lnk in index.links]}"
        )

    def test_at_least_one_embedding_link(self, tmp_path: pathlib.Path) -> None:
        """At least one link has via == 'embedding' or 'both' (embedding recall fires)."""
        index = build_index(
            FIXTURE_REPO,
            output_path=str(tmp_path / "index.json"),
            embeddings=True,
            embedder=FakeEmbedder(),
        )

        embedding_links = [lnk for lnk in index.links if lnk.via in {"embedding", "both"}]
        all_vias = [lnk.via for lnk in index.links]
        assert embedding_links, (
            f"Expected at least one embedding/both link. All vias: {all_vias}"
        )

    def test_no_duplicate_symbol_section_pairs(self, tmp_path: pathlib.Path) -> None:
        """No duplicate (symbol_id, section_id) pairs in index.links."""
        index = build_index(
            FIXTURE_REPO,
            output_path=str(tmp_path / "index.json"),
            embeddings=True,
            embedder=FakeEmbedder(),
        )

        pairs = [(link.symbol_id, link.section_id) for link in index.links]
        assert len(pairs) == len(set(pairs)), (
            f"Duplicate (symbol_id, section_id) pairs found: "
            f"{[p for p in pairs if pairs.count(p) > 1]}"
        )


class TestBuildIndexNoEmbeddings:
    """Tests for build_index with embeddings=False."""

    def test_all_links_are_symbol_match(self, tmp_path: pathlib.Path) -> None:
        """With embeddings=False, every link has via == 'symbol-match'."""
        index = build_index(
            FIXTURE_REPO,
            embeddings=False,
        )

        for link in index.links:
            assert link.via == "symbol-match", (
                f"Expected via='symbol-match', got {link.via!r} for link "
                f"({link.symbol_id}, {link.section_id})"
            )

    def test_links_match_link_by_name_output(self, tmp_path: pathlib.Path) -> None:
        """With embeddings=False, links equal the link_by_name output for the same repo."""
        index = build_index(
            FIXTURE_REPO,
            embeddings=False,
        )

        # Recompute link_by_name directly for comparison
        expected_pairs = {
            (link.symbol_id, link.section_id)
            for link in link_by_name(index.symbols, index.sections)
        }
        actual_pairs = {(link.symbol_id, link.section_id) for link in index.links}

        assert actual_pairs == expected_pairs, (
            f"Link pairs mismatch.\nExtra: {actual_pairs - expected_pairs}\n"
            f"Missing: {expected_pairs - actual_pairs}"
        )

    def test_no_chroma_dir_created(self, tmp_path: pathlib.Path) -> None:
        """With embeddings=False and output in tmp_path, no chroma dir is created."""
        output = tmp_path / "index.json"
        build_index(
            FIXTURE_REPO,
            output_path=str(output),
            embeddings=False,
        )

        chroma_dir = tmp_path / "chroma"
        assert not chroma_dir.exists(), f"chroma dir was unexpectedly created at {chroma_dir}"


class TestRebuildAfterLostIndex:
    """Tests that build_index always produces a clean rebuild with no dangling links."""

    def test_rebuild_after_lost_index_has_no_dangling_links(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Rebuild after lost index.json leaves no dangling embedding links.

        Scenario:
        1. First build with service.ts present — vectors land in chroma.
        2. Delete service.ts AND index.json (simulating lost index but surviving chroma).
        3. Rebuild (full=False) — without the fix, stale service.ts vectors survive in
           chroma and link_by_embedding returns symbol_ids that no longer exist in the
           freshly-built index (dangling links).  With the fix, the store is reset
           unconditionally and no stale vectors remain.

        threshold=0.0 ensures ANY surviving stale vector becomes a link, so the
        pre-fix failure is guaranteed.
        """
        # Step 1: copy fixtures so we can mutate them safely.
        tmp_repo = str(tmp_path / "repo")
        shutil.copytree("tests/fixtures/sample_repo", tmp_repo)
        idx = tmp_path / "index.json"

        build_index(
            tmp_repo,
            output_path=str(idx),
            embeddings=True,
            embedder=FakeEmbedder(),
            threshold=0.0,
        )

        # Step 2: simulate a lost index with surviving chroma data.
        service_ts = os.path.join(tmp_repo, "service.ts")
        os.remove(service_ts)
        os.remove(str(idx))
        # chroma/ directory is intentionally left in place.

        # Step 3: rebuild without full=True.
        index2 = build_index(
            tmp_repo,
            output_path=str(idx),
            embeddings=True,
            embedder=FakeEmbedder(),
            threshold=0.0,
        )

        # Assert: no symbol from the deleted file appears in the rebuilt index.
        for sym_id, sym in index2.symbols.items():
            assert sym.file != "service.ts", (
                f"Stale symbol {sym_id!r} from deleted service.ts found in rebuilt index"
            )

        # Assert: every link references ids that actually exist — no dangling links.
        for link in index2.links:
            assert link.symbol_id in index2.symbols, (
                f"Dangling link: symbol_id {link.symbol_id!r} not in index2.symbols. "
                f"This indicates stale vectors from service.ts survived the rebuild."
            )
            assert link.section_id in index2.sections, (
                f"Dangling link: section_id {link.section_id!r} not in index2.sections."
            )
