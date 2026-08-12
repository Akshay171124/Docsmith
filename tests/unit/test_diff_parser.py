"""Tests for src/detection/diff_parser.py."""

from __future__ import annotations

from src.detection.diff_parser import parse_unified_diff


def test_single_modify_hunk_added_lines():
    diff = """\
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def foo():
-    return 1
+    return 2
+    # extra
     pass
"""
    result = parse_unified_diff(diff)

    assert result == {"app.py": frozenset({2, 3})}


def test_multi_hunk_single_file():
    diff = """\
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def foo():
-    return 1
+    return 2
+    # extra
     pass
@@ -10,3 +11,4 @@
 def bar():
-    return 1
+    return 2
+    # extra
     pass
"""
    result = parse_unified_diff(diff)

    assert result == {"app.py": frozenset({2, 3, 12, 13})}


def test_multiple_files_in_one_diff():
    diff = """\
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def foo():
-    return 1
+    return 2
+    # extra
     pass
--- a/util.py
+++ b/util.py
@@ -1,2 +1,3 @@
 def helper():
+    print("hi")
     pass
"""
    result = parse_unified_diff(diff)

    assert result == {
        "app.py": frozenset({2, 3}),
        "util.py": frozenset({2}),
    }


def test_added_file():
    diff = """\
--- /dev/null
+++ b/new.py
@@ -0,0 +1,3 @@
+def new():
+    return 1
+
"""
    result = parse_unified_diff(diff)

    assert result == {"new.py": frozenset({1, 2, 3})}


def test_pure_deletion_file_maps_to_empty_frozenset():
    diff = """\
--- a/old.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def old():
-    return 1
-
"""
    result = parse_unified_diff(diff)

    assert result == {"old.py": frozenset()}


def test_rename_with_deletion_only_keys_new_path():
    diff = """\
diff --git a/old.py b/new.py
similarity index 90%
rename from old.py
rename to new.py
--- a/old.py
+++ b/new.py
@@ -1,3 +1,2 @@
 def foo():
-    x = 1
     return foo
"""
    result = parse_unified_diff(diff)

    assert result == {"new.py": frozenset()}


def test_skips_files_with_no_hunks():
    diff = """\
diff --git a/img.png b/img.png
index 111..222 100644
Binary files a/img.png and b/img.png differ
"""
    result = parse_unified_diff(diff)

    assert result == {}
