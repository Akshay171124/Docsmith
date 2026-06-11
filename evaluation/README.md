# Evaluation

How we prove Docsmith works. Numbers from here go in the top-level README.

## History replay (headline benchmark) — `history_replay/`

Mine commits that changed **both** code and docs together. The doc edit is ground truth
for what *should* change. Replay: hide the doc edit, feed Docsmith only the code diff, and
measure whether it reproduces the right fix.

- **Detection metrics:** true positives / false positives / false negatives.
- **Correction quality:** exact and semantic match of the generated fix vs. the real edit.

## Curated suite (regression) — `curated/`

Hand-labeled should/shouldn't-update cases on a forked, well-documented repo (e.g.
FastAPI, Pydantic). Stable ground truth; guards against regressions.

## Data — `data/`

Mined datasets and raw run outputs (git-ignored except `.gitkeep`). Dated, like Forge's
`docs/analysis/data/`.

## Reporting — `report.py`

Aggregates runs into the metrics table published in the README.

> Evaluation makes real LLM calls and is intentionally **not** part of `pytest` CI.
