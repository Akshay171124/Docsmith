from evaluation.models import CaseResult
from evaluation.scoring import aggregate_report, score_correction, score_detection
from src.index.embeddings import FakeEmbedder


def test_score_detection_counts():
    assert score_detection({"a", "b"}, {"a", "c"}) == (1, 1, 1)      # tp=a, fp=b, fn=c
    assert score_detection(set(), {"a"}) == (0, 0, 1)                 # missed
    assert score_detection({"a"}, set()) == (0, 1, 0)                 # false positive
    assert score_detection(set(), set()) == (0, 0, 0)                 # clean negative


def test_score_correction_exact_and_similarity():
    emb = FakeEmbedder()
    same = score_correction("Use `f`.", "Use  `f`.\n", emb)          # whitespace-normalized equal
    assert same["exact"] is True and same["similarity"] > 0.99
    diff = score_correction("totally different", "Use `f`.", emb)
    assert diff["exact"] is False and diff["similarity"] < 0.99


def test_aggregate_report_metrics():
    results = [
        CaseResult("p1", tp=1, fp=0, fn=0, corrections=({"exact": True, "similarity": 1.0},)),
        CaseResult("p2", tp=0, fp=0, fn=1),                          # missed one
        CaseResult("n1", tp=0, fp=0, fn=0),                          # clean negative
    ]
    m = aggregate_report(results, suite="curated", backend="fake", model="none")
    assert (m.tp, m.fp, m.fn) == (1, 0, 1)
    assert m.precision == 1.0                                        # 1/(1+0)
    assert m.recall == 0.5                                           # 1/(1+1)
    assert round(m.f1, 3) == 0.667
    assert m.n_corrections == 1 and m.exact_match_rate == 1.0 and m.mean_similarity == 1.0
    assert m.n_cases == 3


def test_aggregate_report_zero_guards():
    m = aggregate_report([CaseResult("n", 0, 0, 0)], suite="s", backend="b", model="m")
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0
    assert m.exact_match_rate == 0.0 and m.mean_similarity == 0.0
