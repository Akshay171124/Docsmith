# Tests

```bash
pip install -r requirements.txt
pytest                 # unit + integration
pytest tests/unit      # fast, no LLM
```

Layout mirrors `src/`. See `TEST_PLAN.md` for the strategy and the deterministic/LLM
boundary. Evaluation benchmarks live in `../evaluation/` and run separately (they make
real LLM calls).
