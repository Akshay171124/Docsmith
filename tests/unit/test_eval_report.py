import json

from evaluation.report import load_run, render_table, update_readme

RUN = {
    "report": {
        "suite": "curated", "backend": "ollama", "model": "qwen2.5-coder:7b", "n_cases": 4,
        "tp": 2, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0,
        "n_corrections": 2, "exact_match_rate": 0.5, "mean_similarity": 0.82,
    },
    "results": [],
}


def test_load_and_render(tmp_path):
    p = tmp_path / "run.json"
    p.write_text(json.dumps(RUN))
    report = load_run(str(p))
    assert report.f1 == 1.0 and report.n_cases == 4
    table = render_table(report)
    assert "Precision" in table and "1.00" in table and "qwen2.5-coder:7b" in table


def test_update_readme_inserts_then_replaces(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Docsmith\n\nintro\n")
    update_readme(str(readme), "TABLE-A")
    first = readme.read_text()
    assert "## Results" in first and "TABLE-A" in first
    update_readme(str(readme), "TABLE-B")
    second = readme.read_text()
    assert "TABLE-B" in second and "TABLE-A" not in second     # replaced, not duplicated
    assert second.count("## Results") == 1
