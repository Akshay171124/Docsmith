import json

from evaluation.corpus import load_curated_cases


def test_loads_case_files(tmp_path):
    (tmp_path / "sig.json").write_text(json.dumps({
        "case_id": "sig",
        "base_files": {"app.py": "def f():\n    return 1\n"},
        "head_files": {"app.py": "def f(x):\n    return x\n"},
        "gold": {"stale_section_ids": ["README.md#users"], "fixes": {}},
    }))
    cases = load_curated_cases(str(tmp_path))
    assert len(cases) == 1
    assert cases[0].case_id == "sig"
    assert cases[0].gold.stale_section_ids == frozenset({"README.md#users"})


def test_ships_starter_corpus_with_positives_and_negatives():
    cases = load_curated_cases()          # the real bundled corpus
    assert len(cases) >= 4
    positives = [c for c in cases if c.gold.stale_section_ids]
    negatives = [c for c in cases if not c.gold.stale_section_ids]
    assert positives and negatives        # corpus measures both recall and precision
