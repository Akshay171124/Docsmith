"""Tests for src/index/hashing.py — hash_file and classify_changes."""
from __future__ import annotations

from src.index.hashing import Changes, classify_changes, hash_file

# ---------------------------------------------------------------------------
# hash_file
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_returns_64_char_lowercase_hex(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_bytes(b"hello")
        digest = hash_file(str(f))
        assert len(digest) == 64
        assert digest == digest.lower()
        assert all(c in "0123456789abcdef" for c in digest)

    def test_identical_content_same_digest(self, tmp_path):
        f1 = tmp_path / "f1.txt"
        f2 = tmp_path / "f2.txt"
        f1.write_bytes(b"same content")
        f2.write_bytes(b"same content")
        assert hash_file(str(f1)) == hash_file(str(f2))

    def test_different_content_different_digest(self, tmp_path):
        f1 = tmp_path / "f1.txt"
        f2 = tmp_path / "f2.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert hash_file(str(f1)) != hash_file(str(f2))


# ---------------------------------------------------------------------------
# classify_changes
# ---------------------------------------------------------------------------


class TestClassifyChanges:
    def test_added_changed_deleted_populated(self):
        current = {"a": "1", "b": "2x", "c": "3"}
        previous = {"a": "1", "b": "2", "d": "4"}
        result = classify_changes(current, previous)
        assert result.added == {"c"}
        assert result.changed == {"b"}
        assert result.deleted == {"d"}

    def test_unchanged_key_appears_in_no_set(self):
        current = {"a": "1", "b": "2x", "c": "3"}
        previous = {"a": "1", "b": "2", "d": "4"}
        result = classify_changes(current, previous)
        assert "a" not in result.added
        assert "a" not in result.changed
        assert "a" not in result.deleted

    def test_no_change_all_sets_empty(self):
        maps = {"x": "hash1", "y": "hash2"}
        result = classify_changes(maps, maps)
        assert result.added == set()
        assert result.changed == set()
        assert result.deleted == set()

    def test_returns_changes_instance(self):
        result = classify_changes({}, {})
        assert isinstance(result, Changes)

    def test_empty_current_all_deleted(self):
        result = classify_changes({}, {"a": "1", "b": "2"})
        assert result.deleted == {"a", "b"}
        assert result.added == set()
        assert result.changed == set()

    def test_empty_previous_all_added(self):
        result = classify_changes({"a": "1", "b": "2"}, {})
        assert result.added == {"a", "b"}
        assert result.deleted == set()
        assert result.changed == set()
