from evaluation.models import Case, CaseResult, Gold, MetricsReport


def test_case_and_gold():
    gold = Gold(stale_section_ids=frozenset({"README.md#users"}), fixes={"README.md#users": "new"})
    case = Case(case_id="c1", base_files={"a.py": "x"}, head_files={"a.py": "y"}, gold=gold)
    assert case.gold.stale_section_ids == frozenset({"README.md#users"})
    assert case.head_files["a.py"] == "y"


def test_result_defaults():
    r = CaseResult(case_id="c1", tp=1, fp=0, fn=0)
    assert r.corrections == ()


def test_metrics_report_fields():
    m = MetricsReport(
        suite="curated", backend="fake", model="none", n_cases=2, tp=1, fp=0, fn=1,
        precision=1.0, recall=0.5, f1=0.666, n_corrections=1, exact_match_rate=1.0,
        mean_similarity=0.9,
    )
    assert m.f1 == 0.666 and m.precision == 1.0
