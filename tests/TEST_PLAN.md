# Test Plan

Docsmith follows TDD: a failing test precedes every new function or behavior change.

## Layers

| Suite | Location | LLM? | What it covers |
|---|---|---|---|
| Unit | `tests/unit/` | No (mocked at `src/llm/client.py`) | Each `src/` module in isolation. |
| Integration | `tests/integration/` | Mocked | Full pipeline over a fixture repo + diff. |
| Evaluation | `../evaluation/` | Real (gated) | Accuracy benchmarks; not part of `pytest` CI. |

## Determinism boundary

Stages 1–4 (diff parse, symbol map, candidate link, triage) MUST be tested with zero LLM
calls — they are pure functions over fixtures. Stages 5–7 (investigator, repair,
validator) mock the Claude client and assert on prompts + handling of structured
responses.

## Fixtures (`tests/fixtures/`)

- Small sample repos in 2–3 languages with known symbols.
- Saved diffs representing each meaningful change kind (rename, default change, new param,
  removed feature, comment-only, whitespace-only).
- Doc sections with known symbol references.

## Priority coverage

- Symbol extraction correctness per language.
- Triage filter never lets noise through and never drops a real signature change.
- Candidate linker precision/recall on fixture pairs.
- Confidence router boundary behavior at the threshold.
- Reporter never produces an auto-merge.
