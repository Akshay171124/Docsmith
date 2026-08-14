from src.detection.source import extract_symbol_source

PY = '''\
def alpha(x):
    return x


def beta(y, z):
    return y + z
'''


def test_extracts_named_symbol_source():
    src = extract_symbol_source(PY, "m.py", "beta")
    assert src == "def beta(y, z):\n    return y + z"


def test_returns_none_when_content_is_none():
    assert extract_symbol_source(None, "m.py", "beta") is None


def test_returns_none_for_unknown_symbol():
    assert extract_symbol_source(PY, "m.py", "gamma") is None


def test_returns_none_for_unsupported_language():
    assert extract_symbol_source("whatever", "notes.txt", "beta") is None
