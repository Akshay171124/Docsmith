"""Smoke test: the src package imports cleanly.

Placeholder so CI has a test to run before the index-core plan is executed; real unit
tests join it during execution.
"""

import importlib


def test_src_package_imports():
    assert importlib.import_module("src") is not None
